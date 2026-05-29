import os
import sys
import uvicorn

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from config import HOST, PORT, AUDIO_TEMP_DIR
from core.database import init_db, close_db
from routers import logs, tts, review, upload
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  #  allow_origins=CORS_ORIGINS
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs(AUDIO_TEMP_DIR, exist_ok=True)
app.mount("/audio", StaticFiles(directory=AUDIO_TEMP_DIR), name="audio")


app.include_router(logs.router)
app.include_router(tts.router)
app.include_router(review.router)
app.include_router(upload.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)


# CUDA_VISIBLE_DEVICES=4
