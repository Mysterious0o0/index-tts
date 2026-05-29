import time
import random
import asyncio
import logging
import builtins
import traceback

from typing import Any
from asynch import connect
from contextlib import asynccontextmanager
from collections.abc import Iterable, Callable, Mapping
from asynch.errors import ProgrammingError, UnexpectedPacketFromServerError


log = logging.getLogger("ch_client")


class _PooledConn:
    """内部封装，跟踪连接元数据，便于健康检查与回收"""

    __slots__ = ("conn", "born_at", "last_used", "in_use", "query_count")

    def __init__(self, conn):
        now = time.time()
        self.conn = conn
        self.born_at = now
        self.last_used = now
        self.in_use = False
        self.query_count = 0

    @property
    def is_closed(self) -> bool:
        return getattr(self.conn, "is_closed", False)

    async def close(self):
        try:
            await self.conn.close()
        except Exception:
            pass


class AsyncCHClient:
    def __init__(
        self,
        *,
        minsize: int = 4,
        maxsize: int = 16,
        health_interval: float = 20.0,  # 健康检查周期（秒）
        max_idle: float = 120.0,  # 单连接最大空闲时间（秒）
        max_lifetime: float = 3600.0,  # 单连接最大生存期（秒）
        max_queries_per_conn: int = 20000,  # 每连接最大查询次数（超过则回收）
        acquire_timeout: float = 10.0,  # 获取连接最长等待时间（秒）
        retry: int = 2,  # 默认重试次数
        base_backoff: float = 0.25,  # 重试起始退避
        backoff_cap: float = 2.0,  # 单次退避上限
        **kwargs,
    ):
        self.kwargs = kwargs
        self.minsize = minsize
        self.maxsize = maxsize
        self.health_interval = health_interval
        self.max_idle = max_idle
        self.max_lifetime = max_lifetime
        self.max_queries_per_conn = max_queries_per_conn
        self.acquire_timeout = acquire_timeout
        self.default_retry = retry
        self.base_backoff = base_backoff
        self.backoff_cap = backoff_cap

        self._pool: list[_PooledConn] = []
        self._active = 0
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(self.maxsize)
        self._initialized = False

        self._hc_task: asyncio.Task | None = None
        self._closing = False

    # 初始化/关闭
    async def init_pool(self):
        async with self._lock:
            if self._initialized:
                return
            for _ in range(min(self.minsize, self.maxsize)):
                c = await connect(**self.kwargs)
                self._pool.append(_PooledConn(c))
            self._initialized = True
            self._closing = False
            if self.health_interval > 0:
                self._hc_task = asyncio.create_task(self._health_check_loop())

    async def close(self):
        self._closing = True
        if self._hc_task:
            self._hc_task.cancel()
            try:
                await self._hc_task
            except asyncio.CancelledError:
                pass
            self._hc_task = None
        async with self._lock:
            for p in self._pool:
                await p.close()
            self._pool.clear()
            self._active = 0
            self._initialized = False

    # 连接获取/释放
    async def _new_conn(self) -> _PooledConn:
        c = await connect(**self.kwargs)
        return _PooledConn(c)

    async def acquire(self) -> _PooledConn:
        await self.init_pool()
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.acquire_timeout)
        except builtins.TimeoutError:
            raise RuntimeError("Connection pool exhausted (acquire timeout)")

        async with self._lock:
            now = time.time()
            while self._pool:
                p = self._pool.pop()
                if p.is_closed or self._should_recycle(p, now):
                    await p.close()
                    continue
                # 获取连接后立即清理状态
                try:
                    async with p.conn.cursor() as cur:
                        try:
                            await cur.fetchall()
                        except ProgrammingError:
                            pass
                except Exception as e:
                    # 清理失败，关闭这个连接，继续找下一个
                    log.warning(
                        f"[database logger] acquire: cleanup failed, closing conn: {e}"
                    )
                    await p.close()
                    continue

                p.in_use = True
                p.last_used = now
                self._active += 1
                return p

            # 无可用空闲连接，新建
            p = await self._new_conn()
            p.in_use = True
            p.last_used = now
            self._active += 1
            return p

    async def release(self, p: _PooledConn, *, force_close: bool = False):
        if p is None:
            return
        # 释放前强制清理游标状态
        try:
            async with p.conn.cursor() as cur:
                try:
                    await cur.fetchall()
                except ProgrammingError:
                    pass
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[database logger] release: cleanup failed: {e}")
            force_close = True  # 清理失败，强制关闭
        p.in_use = False
        p.last_used = time.time()
        async with self._lock:
            self._active = max(0, self._active - 1)
            if force_close or p.is_closed or self._should_recycle(p, p.last_used):
                await p.close()
            else:
                self._pool.append(p)
        self._sem.release()

    def _should_recycle(self, p: _PooledConn, now: float | None = None) -> bool:
        now = now or time.time()
        if self.max_lifetime and (now - p.born_at) > self.max_lifetime:
            return True
        if self.max_idle and (now - p.last_used) > self.max_idle:
            return True
        if self.max_queries_per_conn and p.query_count >= self.max_queries_per_conn:
            return True
        return False

    # 健康检查
    async def _health_check_loop(self):
        try:
            while not self._closing:
                await asyncio.sleep(self.health_interval)
                await self._run_health_check()
        except asyncio.CancelledError:
            return

    async def _run_health_check(self):
        # 只检查空闲连接；坏连接直接剔除
        async with self._lock:
            idle_list = [p for p in self._pool if not p.in_use]
        if not idle_list:
            return

        async def check_one(p: _PooledConn):
            try:
                async with p.conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    # 必须消费结果
                    result = await cur.fetchone()
                    return result is not None
            except Exception:
                return False

        results = await asyncio.gather(
            *(check_one(p) for p in idle_list), return_exceptions=True
        )
        # 删除坏连接
        to_close: list[_PooledConn] = []
        for p, ok in zip(idle_list, results):
            if ok is True:
                continue
            to_close.append(p)

        if to_close:
            async with self._lock:
                for p in to_close:
                    if p in self._pool:
                        self._pool.remove(p)
                    await p.close()

        # 补足最小池
        async with self._lock:
            need = max(0, self.minsize - len(self._pool))
        for _ in range(need):
            try:
                np = await self._new_conn()
            except Exception as e:
                log.warning(f"[database logger] health_check create conn failed: {e}")
                break
            async with self._lock:
                self._pool.append(np)

    # 公共执行工具（确保游标清理）
    @asynccontextmanager
    async def _cursor(self, p: _PooledConn):
        async with p.conn.cursor() as cur:
            try:
                yield cur
            finally:
                # 无论成功失败，尽量清理残留
                try:
                    # 检查是否有未读取的数据
                    if hasattr(cur, "_rows") and cur._rows:
                        await cur.fetchall()
                except ProgrammingError:
                    # INSERT/UPDATE 等操作没有结果集，这是正常的
                    pass
                except Exception as e:
                    # 其他异常：尝试取消查询
                    log.warning(
                        f"[database logger] cursor cleanup failed: {e}, attempting cancel"
                    )
                    try:
                        await cur.cancel()
                    except Exception:
                        pass

    async def _with_retry(self, fn: Callable[[], Any], *, retry: int | None = None):
        retry = self.default_retry if retry is None else retry
        attempt = 0
        while True:
            try:
                return await fn()
            except (
                TimeoutError,
                UnexpectedPacketFromServerError,
                ConnectionResetError,
            ) as e:
                if attempt >= retry:
                    raise
                # 指数退避 + 抖动
                sleep_for = min(self.backoff_cap, self.base_backoff * (2**attempt)) * (
                    1 + random.random()
                )
                log.warning(
                    f"[database logger] transient error: {e}, retrying in {sleep_for:.2f}s (attempt {attempt + 1}/{retry})"
                )
                await asyncio.sleep(sleep_for)
                attempt += 1

    # 写
    async def insert_batch(
        self,
        table_name: str,
        columns: list[str],
        batch_data: list[tuple],
        *,
        retry: int | None = None,
    ):
        if not columns:
            log.error(
                f"[database logger] {table_name} insert: Column list cannot be empty."
            )
            return
        if not batch_data:
            return

        fields = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO `{table_name}` ({fields}) VALUES"

        async def _exec():
            p = await self.acquire()
            try:
                async with self._cursor(p) as cur:
                    await cur.execute(sql, batch_data)
                    p.query_count += 1
            finally:
                # 失败连接在 _with_retry 里抛出异常，由上层捕获；这里一律正常释放
                await self.release(p)

        try:
            await self._with_retry(_exec, retry=retry)
        except Exception:
            log.error(f"[database logger] insert_batch failed for {table_name}")
            log.error(f"[database logger] fields: {fields}")
            sample = batch_data[-5:]
            log.error(
                f"[database logger] sample(-{len(sample)}/{len(batch_data)}): {sample}"
            )
            log.error(f"[database logger] error: {traceback.format_exc()}")
            raise

    async def execute_noresult(
        self,
        sql: str,
        params: Iterable[Any] | None = None,
        *,
        retry: int | None = None,
    ):
        async def _exec():
            p = await self.acquire()
            try:
                async with self._cursor(p) as cur:
                    if params is not None:
                        await cur.execute(sql, params)
                    else:
                        await cur.execute(sql)
                    p.query_count += 1
            finally:
                await self.release(p)

        await self._with_retry(_exec, retry=retry)

    # 读
    async def fetch_all(
        self,
        query: str,
        params: Mapping[str, Any] | Iterable[Any] | None = None,
        *,
        retry: int | None = None,
    ) -> list[tuple]:
        async def _exec():
            p = await self.acquire()
            try:
                async with self._cursor(p) as cur:
                    if params is not None:
                        await cur.execute(query, params)
                    else:
                        await cur.execute(query)
                    rows = await cur.fetchall()
                    p.query_count += 1
                    return rows or []
            finally:
                await self.release(p)

        try:
            return await self._with_retry(_exec, retry=retry)
        except Exception:
            log.error(f"[database logger] fetch_all error: {traceback.format_exc()}")
            return []

    async def fetch_one(
        self,
        query: str,
        params: Mapping[str, Any] | Iterable[Any] | None = None,
        *,
        retry: int | None = None,
    ) -> tuple | None:
        async def _exec():
            p = await self.acquire()
            try:
                async with self._cursor(p) as cur:
                    if params is not None:
                        await cur.execute(query, params)
                    else:
                        await cur.execute(query)
                    row = await cur.fetchone()
                    # 清理剩余（_cursor finally 会做兜底）
                    p.query_count += 1
                    return row
            finally:
                await self.release(p)

        try:
            return await self._with_retry(_exec, retry=retry)
        except Exception:
            log.error(f"[database logger] fetch_one error: {traceback.format_exc()}")
            return None

    # 并发批量写
    async def concurrent_insert(
        self, *batch_tasks: list[tuple[str, list[str], list[tuple]]]
    ):
        tasks = [
            self.insert_batch(table, cols, data)
            for table, cols, data in batch_tasks
            if data
        ]
        if tasks:
            await asyncio.gather(*tasks)
