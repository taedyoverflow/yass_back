from celery import chain
from celery_worker import celery_app
from mytts import run_tts_task
from audio_utils import download_audio, separate_audio
from storage_utils import upload_to_minio, delete_from_minio
import tempfile
import os
import logging
import shutil
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # 로그 수준 설정 (필요 시 조정 가능)

@celery_app.task
def schedule_deletion(bucket: str, object_name: str):
    """600초 뒤 해당 파일 삭제"""
    logger.info(f"🗑️ 삭제 예약 - bucket: {bucket}, object: {object_name}")
    delete_from_minio(bucket, object_name)


@celery_app.task(bind=True)
def tts_task(self, text: str, voice: str):
    temp_dir = tempfile.mkdtemp()
    try:
        unique_id = uuid.uuid4().hex
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tts_output_{timestamp}_{unique_id}.wav"
        output_path = os.path.join(temp_dir, filename)

        logger.info("🗣️ TTS 작업 시작")
        run_tts_task(text, voice, output_path)

        url = upload_to_minio(output_path, "tts-bucket", filename)
        logger.info(f"✅ TTS 업로드 완료 - URL: {url}")

        # 600초 뒤 삭제 예약
        schedule_deletion.apply_async(
            args=["tts-bucket", filename],
            countdown=600
        )
        logger.info("🕒 TTS 삭제 예약 완료 (600초 후)")

        return {"url": url}
    except Exception as e:
        logger.error(f"❌ TTS 작업 실패: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)


@celery_app.task(bind=True)
def process_audio_task(self, youtube_url: str):
    logger.info("🚀 process_audio_task 시작")
    temp_dir = tempfile.mkdtemp()
    logger.info(f"📁 임시 폴더 생성됨: {temp_dir}")

    try:
        logger.info(f"🔗 유튜브 오디오 다운로드 시작: {youtube_url}")
        input_path = download_audio(youtube_url, temp_dir)
        logger.info(f"✅ 다운로드 완료: {input_path}")

        logger.info("🎧 Spleeter 분리 시작")
        vocals, accomp = separate_audio(input_path, temp_dir)
        logger.info(f"✅ 분리 완료 - vocals: {vocals}, accomp: {accomp}")

        # 고유한 파일명 생성
        unique_id = uuid.uuid4().hex
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vocal_name = f"vocals_{timestamp}_{unique_id}.wav"
        accomp_name = f"accompaniment_{timestamp}_{unique_id}.wav"

        vocal_path_final = os.path.join(temp_dir, vocal_name)
        accomp_path_final = os.path.join(temp_dir, accomp_name)

        # 이름 변경 (복사)
        shutil.copyfile(vocals, vocal_path_final)
        shutil.copyfile(accomp, accomp_path_final)

        logger.info("☁️ MinIO 업로드 시작")
        vocal_url = upload_to_minio(vocal_path_final, "separation-bucket", vocal_name)
        accomp_url = upload_to_minio(accomp_path_final, "separation-bucket", accomp_name)
        logger.info(f"✅ 업로드 완료 - vocal_url: {vocal_url}, accomp_url: {accomp_url}")

        logger.info("🕒 600초 후 삭제 예약 시작")
        schedule_deletion.apply_async(args=["separation-bucket", vocal_name], countdown=600)
        schedule_deletion.apply_async(args=["separation-bucket", accomp_name], countdown=600)
        logger.info("✅ 삭제 예약 완료")

        return {
            "vocal_url": vocal_url,
            "accompaniment_url": accomp_url
        }

    except Exception as e:
        logger.error(f"❌ 예외 발생: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)

logger.info("🐍 최종 celery_task.py 로딩 완료됨")
