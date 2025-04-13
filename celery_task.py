from celery import chain
from celery_worker import celery_app
from mytts import run_tts_task
from audio_utils import download_audio, separate_audio
from storage_utils import upload_to_minio, delete_from_minio
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

@celery_app.task
def schedule_deletion(bucket: str, object_name: str):
    """60초 뒤 해당 파일 삭제"""
    delete_from_minio(bucket, object_name)

@celery_app.task(bind=True)
def tts_task(self, text: str, voice: str):
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "tts_output.mp3")
    try:
        run_tts_task(text, voice, output_path)
        filename = os.path.basename(output_path)
        url = upload_to_minio(output_path, "tts-bucket", filename)

        # 60초 뒤 삭제 예약
        schedule_deletion.apply_async(
            args=["tts-bucket", filename],
            countdown=60
        )

        return {"url": url}
    except Exception as e:
        raise self.retry(exc=e, countdown=10, max_retries=3)
    
@celery_app.task(bind=True)
def process_audio_task(self, youtube_url: str):
    logger.info("🚀 process_audio_task 시작")
    temp_dir = tempfile.mkdtemp()
    print(f"📁 임시 폴더 생성됨: {temp_dir}")

    try:
        print(f"🔗 유튜브 오디오 다운로드 시작: {youtube_url}")
        input_path = download_audio(youtube_url, temp_dir)
        print(f"✅ 다운로드 완료: {input_path}")

        print("🎧 Spleeter 분리 시작")
        vocals, accomp = separate_audio(input_path, temp_dir)
        print(f"✅ 분리 완료 - vocals: {vocals}, accomp: {accomp}")

        vocal_name = os.path.basename(vocals)
        accomp_name = os.path.basename(accomp)

        print("☁️ MinIO 업로드 시작")
        vocal_url = upload_to_minio(vocals, "separation-bucket", vocal_name)
        accomp_url = upload_to_minio(accomp, "separation-bucket", accomp_name)
        print(f"✅ 업로드 완료 - vocal_url: {vocal_url}, accomp_url: {accomp_url}")

        print("🕒 60초 후 삭제 예약 시작")
        schedule_deletion.apply_async(args=["separation-bucket", vocal_name], countdown=60)
        schedule_deletion.apply_async(args=["separation-bucket", accomp_name], countdown=60)
        print("✅ 삭제 예약 완료")

        return {
            "vocal_url": vocal_url,
            "accompaniment_url": accomp_url
        }

    except Exception as e:
        print(f"❌ 예외 발생: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)

print("🐍 최종 celery_task.py 로딩 완료됨")