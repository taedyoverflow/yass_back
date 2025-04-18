import os
import subprocess
from spleeter.separator import Separator
import threading
import logging
import tempfile
import shutil
import uuid
from datetime import datetime
from celery import Celery
from celery_worker import celery_app
from mytts import run_tts_task
from audio_utils import download_audio, separate_audio
from storage_utils import upload_to_minio, delete_from_minio
import traceback

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 🎯 파일명 생성 헬퍼
def generate_unique_filename(prefix: str, ext: str = "wav") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex
    return f"{prefix}_{timestamp}_{unique_id}.{ext}"

# 🎯 MinIO 업로드 후 삭제 예약
def upload_with_deletion(bucket: str, file_path: str, object_name: str) -> str:
    url = upload_to_minio(file_path, bucket, object_name)
    schedule_deletion.apply_async(args=[bucket, object_name], countdown=600)
    logger.info(f"🕒 삭제 예약 완료 (600초 후): {object_name}")
    return url

@celery_app.task
def schedule_deletion(bucket: str, object_name: str):
    logger.info(f"🗑️ 삭제 예약 - bucket: {bucket}, object: {object_name}")
    delete_from_minio(bucket, object_name)

@celery_app.task(bind=True)
def process_audio_task(self, youtube_url: str):
    logger.info("🚀 process_audio_task 시작")
    temp_dir = tempfile.mkdtemp()
    logger.info(f"📁 임시 폴더 생성됨: {temp_dir}")

    try:
        # 1. 다운로드
        logger.info(f"🔗 유튜브 오디오 다운로드 시작: {youtube_url}")
        input_path = download_audio(youtube_url, temp_dir)
        logger.info(f"✅ 다운로드 완료: {input_path}")

        # 2. 분리
        logger.info("🎧 Spleeter 분리 시작")
        vocals_path, accomp_path = separate_audio(input_path, temp_dir)
        logger.info("✅ 분리 완료")

        # 3. 파일명 생성
        vocal_name = generate_unique_filename("vocals")
        accomp_name = generate_unique_filename("accompaniment")

        # 4. 복사 및 이름변경
        vocal_final = os.path.join(temp_dir, vocal_name)
        accomp_final = os.path.join(temp_dir, accomp_name)
        shutil.copyfile(vocals_path, vocal_final)
        shutil.copyfile(accomp_path, accomp_final)

        # 5. 업로드 및 삭제예약
        logger.info("☁️ MinIO 업로드 시작")
        vocal_url = upload_with_deletion("separation-bucket", vocal_final, vocal_name)
        accomp_url = upload_with_deletion("separation-bucket", accomp_final, accomp_name)
        logger.info("✅ 모든 업로드 및 삭제예약 완료")

        return {
            "vocal_url": vocal_url,
            "accompaniment_url": accomp_url
        }

    except Exception as e:
        logger.error("❌ 예외 발생:")
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10, max_retries=3)

    finally:
        # 항상 정리
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"🧹 임시 폴더 정리 완료: {temp_dir}")
