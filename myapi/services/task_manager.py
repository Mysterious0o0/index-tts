"""
异步任务进度管理（内存级，重启丢失）。
生产环境可替换为 Redis。
"""

import uuid
from datetime import datetime

_tasks: dict[str, dict] = {}


def create_task(task_type: str) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "task_id": task_id,
        "type": task_type,
        "status": "pending",  # pending / running / done / failed
        "total": 0,
        "done": 0,
        "failed": 0,
        "failed_ids": [],
        "created_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
    }
    return task_id


def get_task(task_id: str) -> dict | None:
    return _tasks.get(task_id)


def get_all_tasks() -> list[dict]:
    return list(_tasks.values())


def update_task(task_id: str, **kwargs):
    if task_id in _tasks:
        _tasks[task_id].update(kwargs)


def update_progress(task_id: str, done: int, total: int, failed_ids: list = None):
    if task_id in _tasks:
        _tasks[task_id]["done"] = done
        _tasks[task_id]["total"] = total
        if failed_ids is not None:
            _tasks[task_id]["failed"] = len(failed_ids)
            _tasks[task_id]["failed_ids"] = failed_ids


def finish_task(task_id: str, success: bool, error: str = None):
    if task_id in _tasks:
        _tasks[task_id]["status"] = "done" if success else "failed"
        _tasks[task_id]["finished_at"] = datetime.now().isoformat()
        if error:
            _tasks[task_id]["error"] = error
