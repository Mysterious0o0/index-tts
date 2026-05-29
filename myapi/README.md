# myapi — TTS 音频管理后端

基于 FastAPI 的 TTS 音频生成与审核管理系统，作为 B 服务器运行，负责音频生成、审核、上传 OSS 等内部处理任务。

## 架构概览

```
A 服务器（主站）                    B 服务器（本服务）
     │                                    │
     │  ← 拉取日志                         │
     │  写入 ClickHouse                    │
     │                                    │
     │                                    ├── IndexTTS-2 模型推理 → 本地 wav
     │                                    ├── 审核通过/删除
     │                                    ├── 上传 OSS
     │                                    │
     │  ← 触发重建 Faiss 索引 ←────────────┘
```

## 功能模块

| 模块 | 路由前缀 | 说明 |
|------|----------|------|
| 日志拉取 | `/logs` | 从 A 服务器拉取每日日志文件，解析 text+level 写入 ClickHouse |
| TTS 生成 | `/tts` | 调用 IndexTTS-2 批量生成音频，按 level（1/2/3）匹配对应 prompt wav |
| 审核管理 | `/review` | 分页查询、批次筛选、审核通过/删除记录 |
| OSS 上传 | `/upload` | 批量上传已审核音频到阿里云 OSS，完成后通知 A 重建索引 |
| 健康检查 | `/health` | 服务探活 |

## 数据流程

```
日志拉取 ──→ pending_review ──→ TTS 生成 ──→ pending_review（带本地音频）
                                                  │
                                         审核 ────┴──── 删除（终态）
                                          │
                                    approved ──→ OSS 上传 ──→ uploaded
                                          │
                                   upload_failed（可重试）
```

## 技术栈

- **Web 框架**: FastAPI + Uvicorn
- **数据库**: ClickHouse（ReplacingMergeTree，通过 asynch 异步驱动）
- **对象存储**: 阿里云 OSS
- **TTS 模型**: IndexTTS-2（支持 FP16 + CUDA Kernel + DeepSpeed）
- **HTTP 客户端**: httpx

## 快速开始

### 环境要求

- Python 3.10+
- NVIDIA GPU（用于 TTS 推理）
- ClickHouse 服务
- 阿里云 OSS Bucket


### 依赖安装

```bash
pip install -r requirements.txt
```

TTS 模型依赖需单独安装：

```bash
pip install indextts   # 或按 IndexTTS2 项目文档安装
```

---

### 环境变量配置

复制模板并填写：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `CLICKHOUSE_HOST` | A 服务器 IP |
| `CLICKHOUSE_PORT` | ClickHouse 端口，默认 9000 |
| `CLICKHOUSE_USER` | 读写账号，对应 `init_clickhouse.sql` 里创建的 `b_writer` |
| `CLICKHOUSE_PASSWORD` | b_writer 密码 |
| `CLICKHOUSE_DB` | 数据库名，默认 `audio_db` |
| `OSS_ACCESS_KEY_ID` | 阿里云 AccessKey ID |
| `OSS_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret |
| `OSS_ENDPOINT` | OSS 地域端点，如 `oss-cn-hangzhou.aliyuncs.com` |
| `OSS_BUCKET` | Bucket 名称 |
| `OSS_AUDIO_PREFIX` | OSS 存储路径前缀，默认 `depthVoice/` |
| `TTS_CFG_PATH` | IndexTTS2 config.yaml 路径 |
| `TTS_MODEL_DIR` | IndexTTS2 模型目录 |
| `TTS_PROMPT_WAV_DIR` | prompt wav 目录，对应 `examples/gen/`，需包含 level1.WAV / level2.WAV / level3.WAV |
| `AUDIO_TEMP_DIR` | 生成音频临时目录（上传 OSS 前存放） |
| `LOG_FETCH_URL` | A 服务器日志文件接口地址 |
| `LOG_FETCH_TOKEN` | 日志接口鉴权 Token |
| `SERVER_A_REBUILD_URL` | A 服务器 Faiss 索引重建接口地址 |
| `SERVER_A_REBUILD_TOKEN` | 重建接口鉴权 Token |
| `CORS_ORIGINS` | 跨域白名单，填 A 服务器地址 |

---

### 启动

```bash
python main.py
# 默认监听 0.0.0.0:9976
```

## API 接口

### 日志

```
POST /logs/fetch         拉取指定日期日志，解析后写入 ClickHouse
Body: { "date": "2025-01-01" }  # 不填默认今天
```

### TTS 生成

```
POST /tts/generate       触发批量音频生成（异步）
Body: { "batch_id": "...", "level": "1" }

GET  /tts/progress/{id}  查询生成任务进度
```

### 审核

```
GET    /review/list      分页查询记录（支持 status/level/batch_id 筛选）
GET    /review/batches   获取批次列表（用于下拉筛选）
POST   /review/{id}/approve  审核通过
DELETE /review/{id}      删除记录
```

### OSS 上传

```
POST /upload/batch       批量上传所有 approved 记录
POST /upload/retry       重试所有 upload_failed 记录
GET  /upload/progress/{id}  查询上传进度
GET  /upload/tasks       列出所有上传任务
```

## 状态说明

| status | 含义 |
|--------|------|
| `pending_review` | 待审核（初始状态/已生成音频） |
| `approved` | 审核通过，等待上传 |
| `uploading` | 上传中 |
| `uploaded` | 已上传 OSS |
| `upload_failed` | 上传失败，可重试 |
| `deleted` | 已删除（终态） |
