import os
import tempfile
import shutil

from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult
from celery_worker import celery_app
from celery_task import (
    tts_task,
    process_audio_task,
    midi_conversion_task,
    process_audio_demucs_task,
    stt_task,
    upload_with_deletion,
    generate_unique_filename,
)
from fastapi.middleware.cors import CORSMiddleware
from youtube_utils import get_video_duration, validate_youtube_exists
from fastapi import UploadFile, File
from mystt import (
    ALLOWED_LANGUAGES,
    ALLOWED_MODES,
    ALLOWED_MODEL_SIZES,
    MAX_STT_DURATION_SEC,
    MAX_STT_UPLOAD_BYTES,
    get_audio_duration_seconds,
    is_allowed_stt_filename,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 또는 ["http://localhost:3000"]로 제한 가능
    allow_credentials=True,
    allow_methods=["*"],  # OPTIONS 포함
    allow_headers=["*"],
)

class YoutubeURL(BaseModel):
    url: str

@app.post("/tts/")
def submit_tts(text: str = Form(...), voice: str = Form(...)):
    task = tts_task.delay(text, voice)
    return {"task_id": task.id}

@app.post("/process_audio/")
def submit_audio(youtube: YoutubeURL):
    if not validate_youtube_exists(youtube.url):
        raise HTTPException(
            status_code=404,
            detail="해당 유튜브 영상이 존재하지 않거나 접근할 수 없습니다."
        )

    duration = get_video_duration(youtube.url)
    if duration == -1:
        raise HTTPException(
            status_code=500,
            detail="영상 길이를 확인할 수 없습니다. 잠시 후 다시 시도해주세요."
        )

    if duration > 360:
        raise HTTPException(
            status_code=400,
            detail="6분을 초과하는 유튜브 영상은 분리할 수 없습니다."
        )

    task = process_audio_task.delay(youtube.url)
    return {"task_id": task.id}

@app.get("/status/{task_id}")
def get_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {"task_id": task_id, "status": result.status}

@app.get("/result/{task_id}")
async def get_task_result(task_id: str):
    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING":
        return {"status": "PENDING"}

    if result.state == "FAILURE":
        return {"status": "FAILURE"}

    if result.state == "SUCCESS":
        data = result.result
        response = {
            "status": "SUCCESS"
        }

        if isinstance(data, dict):
            if "midi_url" in data:
                response["midi_url"] = data["midi_url"]
            if "sheet_url" in data:
                response["sheet_url"] = data["sheet_url"]
            if "bpm" in data:
                response["bpm"] = data["bpm"]
            if "vocal_url" in data:
                response["vocal_url"] = data["vocal_url"]
            if "accompaniment_url" in data:
                response["accompaniment_url"] = data["accompaniment_url"]
            if "drums_url" in data:
                response["drums_url"] = data["drums_url"]
            if "bass_url" in data:
                response["bass_url"] = data["bass_url"]
            if "other_url" in data:
                response["other_url"] = data["other_url"]
            if "url" in data:  # TTS용
                response["url"] = data["url"]
            if "text" in data:  # STT용
                response["text"] = data["text"]
            if "transcript_url" in data:
                response["transcript_url"] = data["transcript_url"]

        return response

    return {"status": result.state}

@app.post("/stt/")
async def submit_stt(
    file: UploadFile = File(...),
    language: str = Form("ko"),
    mode: str = Form("intended"),
    model_size: str = Form("turbo"),
):
    """
    음성 파일 업로드 → MinIO 저장 → Celery STT.
    대용량(최대 2시간)은 Redis로 bytes를 넘기지 않음.
    """
    filename = file.filename or ""
    if not is_allowed_stt_filename(filename):
        raise HTTPException(
            status_code=400,
            detail="지원 형식: wav, mp3, m4a, aac, ogg, webm, flac, mp4, 3gp, amr, caf, opus",
        )

    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(status_code=400, detail="language는 ko / en / auto 중 하나여야 합니다.")
    if mode not in ALLOWED_MODES:
        raise HTTPException(status_code=400, detail="mode는 intended / verbatim 중 하나여야 합니다.")
    if model_size not in ALLOWED_MODEL_SIZES:
        raise HTTPException(status_code=400, detail="model_size는 small / turbo / medium 중 하나여야 합니다.")

    ext = os.path.splitext(filename)[1].lower()
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, f"upload{ext}")

    try:
        size = 0
        with open(input_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_STT_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail="파일 크기가 너무 큽니다. 최대 1.6GB까지 업로드할 수 있습니다.",
                    )
                out.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")

        try:
            duration = get_audio_duration_seconds(input_path)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="오디오 길이를 확인할 수 없습니다. 지원되는 음성 파일인지 확인해주세요.",
            )

        if duration > MAX_STT_DURATION_SEC:
            raise HTTPException(
                status_code=400,
                detail="2시간(7200초)을 초과하는 음성 파일은 변환할 수 없습니다.",
            )

        object_name = generate_unique_filename("stt_input", ext=ext.lstrip("."))
        # 긴 CPU 전사 동안 입력 파일이 남아 있도록 8시간 후 삭제
        upload_with_deletion("stt-bucket", input_path, object_name, countdown=28800)

        task = stt_task.delay(
            "stt-bucket",
            object_name,
            ext,
            language,
            mode,
            model_size,
        )
        return {"task_id": task.id}

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/convert_midi/")
async def submit_midi(file: UploadFile = File(...)):
    file_bytes = await file.read()
    task = midi_conversion_task.delay(file_bytes)
    return {"task_id": task.id}

@app.post("/process_audio_demucs/")
def submit_audio_demucs(youtube: YoutubeURL):
    if not validate_youtube_exists(youtube.url):
        raise HTTPException(
            status_code=404,
            detail="해당 유튜브 영상이 존재하지 않거나 접근할 수 없습니다."
        )

    duration = get_video_duration(youtube.url)
    if duration == -1:
        raise HTTPException(
            status_code=500,
            detail="영상 길이를 확인할 수 없습니다. 잠시 후 다시 시도해주세요."
        )

    if duration > 360:
        raise HTTPException(
            status_code=400,
            detail="6분을 초과하는 유튜브 영상은 분리할 수 없습니다."
        )

    task = process_audio_demucs_task.delay(youtube.url)
    return {"task_id": task.id}