from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult
from celery_worker import celery_app
from celery_task import tts_task, process_audio_task
from fastapi.middleware.cors import CORSMiddleware
from youtube_utils import get_video_duration, validate_youtube_exists

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
            detail="❌ 해당 유튜브 영상이 존재하지 않거나 접근할 수 없습니다."
        )

    duration = get_video_duration(youtube.url)
    if duration == -1:
        raise HTTPException(
            status_code=500,
            detail="⛔ 영상 길이를 확인할 수 없습니다. 잠시 후 다시 시도해주세요."
        )

    if duration > 360:
        raise HTTPException(
            status_code=400,
            detail="❌ 6분을 초과하는 유튜브 영상은 분리할 수 없습니다."
        )

    task = process_audio_task.delay(youtube.url)
    return {"task_id": task.id}


@app.get("/status/{task_id}")
def get_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {"task_id": task_id, "status": result.status}

@app.get("/result/{task_id}")
def get_result(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.successful():
        return result.result
    elif result.failed():
        raise HTTPException(status_code=500, detail="처리 실패")
    else:
        return {"status": result.status}
