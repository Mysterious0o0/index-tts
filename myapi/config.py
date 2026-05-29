import os
from dotenv import load_dotenv

load_dotenv()

# server
HOST = "0.0.0.0"
PORT = 9976


# ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "your_server_a_ip")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "b_writer")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "audio_db")

# 阿里云 OSS
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
OSS_REGION = os.getenv("OSS_REGION", "")
OSS_BUCKET = os.getenv("OSS_BUCKET", "your-bucket")
OSS_AUDIO_PREFIX = os.getenv("OSS_AUDIO_PREFIX", "")


# TTS 模型
TTS_CFG_PATH = os.getenv(
    "TTS_CFG_PATH", "/data/nvme2/model/IndexTeam/IndexTTS-2/config.yaml"
)
TTS_MODEL_DIR = os.getenv("TTS_MODEL_DIR", "/data/nvme2/model/IndexTeam/IndexTTS-2/")
# prompt wav 目录，对应 examples/gen/  里的 level1.WAV / level2.WAV / level3.WAV
TTS_PROMPT_WAV_DIR = os.getenv(
    "TTS_PROMPT_WAV_DIR", "/root/code/index-tts/examples/gen"
)

# 音频临时目录
AUDIO_TEMP_DIR = os.getenv("AUDIO_TEMP_DIR", "/data/nvme0/code/temp/indexTTS/")

# A 服务器日志文件接口
LOG_FETCH_URL = os.getenv("LOG_FETCH_URL", "http://ai.peihon.com/dollTest/audio")

# A 服务器 Faiss 索引重建接口
SERVER_A_REBUILD_URL = os.getenv(
    "SERVER_A_REBUILD_URL", "http://your_server_a_ip/internal/index/rebuild"
)
SERVER_A_REBUILD_TOKEN = os.getenv("SERVER_A_REBUILD_TOKEN", "your_internal_token")

# 跨域白名单（A 服务器地址）
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://your_server_a_ip").split(",")
