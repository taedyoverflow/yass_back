from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult
from celery_worker import celery_app
from celery_task import tts_task, process_audio_task
from fastapi.middleware.cors import CORSMiddleware


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
