import os
import asyncio
import tempfile
import shutil
import subprocess
import threading
import time
import traceback
import datetime
from typing import Tuple
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from spleeter.separator import Separator
import tensorflow as tf

app = FastAPI()

# 전역 락: 동시에 하나의 요청만 처리
spleeter_lock = asyncio.Lock()
separator_instance = None
separator_lock = asyncio.Lock()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("🔥 예외 발생 🔥")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class YoutubeURL(BaseModel):
    url: str

def download_audio_temp(youtube_url: str, temp_dir: str) -> str:
    file_name = "input.mp3"
    output_path = os.path.join(temp_dir, file_name)

    command = [
        "sudo", "-u", "user1",
        "/home/user1/.local/bin/yt-dlp",
        "--cookies-from-browser", "chrome",
        "-x", "--audio-format", "mp3",
        "-o", output_path,
        youtube_url
    ]

    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output_path
    except subprocess.CalledProcessError as e:
        print("🛑 yt-dlp 실패 로그 ↓↓↓↓↓")
        print(e.stderr.decode())  # 💥 에러 내용을 서버 로그에 출력
        raise HTTPException(status_code=500, detail=f"Audio download failed: {e.stderr.decode()}")


def create_separator():
    return Separator('spleeter:2stems')

async def get_or_create_separator():
    global separator_instance
    async with separator_lock:
        if separator_instance is None:
            separator_instance = await asyncio.to_thread(create_separator)
        return separator_instance

async def spleeter_separate(audio_path: str, temp_dir: str) -> Tuple[str, str]:
    separator = await get_or_create_separator()
    await asyncio.to_thread(separator.separate_to_file, audio_path, temp_dir, codec="wav")

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    vocal_path = os.path.join(temp_dir, base_name, "vocals.wav")
    accompaniment_path = os.path.join(temp_dir, base_name, "accompaniment.wav")

    if not (os.path.exists(vocal_path) and os.path.exists(accompaniment_path)):
        raise HTTPException(status_code=500, detail="Separated files not found.")

    return vocal_path, accompaniment_path

deleted_dirs = set()
lock = threading.Lock()

def safe_cleanup(cleanup_dir: str):
    with lock:
        if cleanup_dir in deleted_dirs:
            return
        deleted_dirs.add(cleanup_dir)

    time.sleep(60)
    print(f"[CLEANUP] Deleting temp dir: {cleanup_dir}")
    shutil.rmtree(cleanup_dir, ignore_errors=True)

async def async_stream_file_and_cleanup(file_path: str, cleanup_dir: str):
    print(f"▶️ [STREAM] Start streaming: {file_path}")
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk
    finally:
        print(f"🪹 [CLEANUP] Trigger cleanup for: {cleanup_dir}")
        threading.Thread(target=safe_cleanup, args=(cleanup_dir,)).start()

@app.post("/process_audio/")
async def process_audio(youtube: YoutubeURL):
    async with spleeter_lock:
        print("✅ [STEP1] 유튜브 URL 수신:", youtube.url)
        temp_dir = tempfile.mkdtemp()
        print("✅ [STEP2] 임시 디렉터리 생성:", temp_dir)
        try:
            input_audio = await asyncio.get_event_loop().run_in_executor(
                None, download_audio_temp, youtube.url, temp_dir
            )
            print("✅ [STEP3] 오디오 다운로드 완료:", input_audio)

            vocal_path, accompaniment_path = await spleeter_separate(input_audio, temp_dir)
            print("✅ [STEP4] 스플리터 완료")

            base_name = os.path.splitext(os.path.basename(input_audio))[0]
            print(f"✅ [STEP5] 응답 준비 완료: {base_name}")

            return {
                "vocal_stream_url": f"/stream/vocal/{os.path.basename(temp_dir)}/{base_name}",
                "accompaniment_stream_url": f"/stream/accompaniment/{os.path.basename(temp_dir)}/{base_name}"
            }
        except Exception as e:
            print("❌ 예외 발생:")
            traceback.print_exc()
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/stream/{track_type}/{temp_id}/{base_name}")
async def stream_audio(track_type: str, temp_id: str, base_name: str):
    print(f"🎷 [STREAM REQUEST] type={track_type}, temp_id={temp_id}, base_name={base_name}")

    filename_map = {
        "vocal": "vocals.wav",
        "accompaniment": "accompaniment.wav"
    }

    if track_type not in filename_map:
        print("⚠️ [ERROR] Invalid track type:", track_type)
        raise HTTPException(status_code=400, detail="Invalid track type")

    temp_base = os.path.join(tempfile.gettempdir(), temp_id)
    file_path = os.path.join(temp_base, base_name, filename_map[track_type])

    print("📂 [CHECK FILE] Looking for:", file_path)

    if not os.path.exists(file_path):
        print("❌ [ERROR] File not found:", file_path)
        raise HTTPException(status_code=404, detail="File not found.")

    print(f"🚀 [STREAM START] Begin streaming: {file_path}")

    return StreamingResponse(
        async_stream_file_and_cleanup(file_path, temp_base),
        media_type="audio/wav"
    )