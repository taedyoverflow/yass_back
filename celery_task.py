import os
import subprocess
import librosa  # ✅ 이거 추가
import numpy as np
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
from audio_utils import download_audio, separate_audio, separate_audio_demucs
from storage_utils import upload_to_minio, delete_from_minio
import traceback
from basicpitch_utils import convert_to_midi, convert_midi_to_pdf


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 파일명 생성 헬퍼
def generate_unique_filename(prefix: str, ext: str = "wav") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex
    return f"{prefix}_{timestamp}_{unique_id}.{ext}"

# MinIO 업로드 후 삭제 예약
def upload_with_deletion(bucket: str, file_path: str, object_name: str, countdown: int = 360) -> str:
    url = upload_to_minio(file_path, bucket, object_name)
    schedule_deletion.apply_async(args=[bucket, object_name], countdown=countdown)
    logger.info(f"삭제 예약 완료 ({countdown}초 후): {object_name}")
    return url

@celery_app.task
def schedule_deletion(bucket: str, object_name: str):
    logger.info(f"삭제 예약 - bucket: {bucket}, object: {object_name}")
    delete_from_minio(bucket, object_name)

@celery_app.task(bind=True)
def process_audio_task(self, youtube_url: str):
    logger.info("process_audio_task 시작")
    temp_dir = tempfile.mkdtemp()
    logger.info(f"임시 폴더 생성됨: {temp_dir}")

    try:
        logger.info(f"유튜브 오디오 다운로드 시작: {youtube_url}")
        input_path = download_audio(youtube_url, temp_dir)
        logger.info(f"다운로드 완료: {input_path}")

        logger.info("Spleeter 분리 시작")
        vocals_path, accomp_path = separate_audio(input_path, temp_dir)
        logger.info("분리 완료")

        vocal_name = generate_unique_filename("vocals")
        accomp_name = generate_unique_filename("accompaniment")

        vocal_final = os.path.join(temp_dir, vocal_name)
        accomp_final = os.path.join(temp_dir, accomp_name)
        shutil.copyfile(vocals_path, vocal_final)
        shutil.copyfile(accomp_path, accomp_final)

        logger.info("MinIO 업로드 시작")
        vocal_url = upload_with_deletion("separation-bucket", vocal_final, vocal_name)
        accomp_url = upload_with_deletion("separation-bucket", accomp_final, accomp_name)
        logger.info("모든 업로드 및 삭제예약 완료")

        return {
            "vocal_url": vocal_url,
            "accompaniment_url": accomp_url
        }

    except Exception as e:
        logger.error("예외 발생:")
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10, max_retries=3)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"임시 폴더 정리 완료: {temp_dir}")

@celery_app.task(bind=True)
def tts_task(self, text: str, voice: str):
    temp_dir = tempfile.mkdtemp()
    try:
        filename = generate_unique_filename("tts")
        output_path = os.path.join(temp_dir, filename)

        logger.info("TTS 작업 시작")
        run_tts_task(text, voice, output_path)

        url = upload_with_deletion("tts-bucket", output_path, filename)
        logger.info(f"TTS 업로드 및 삭제 예약 완료 - URL: {url}")

        return {"url": url}
    except Exception as e:
        logger.error(f"TTS 작업 실패: {e}")
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10, max_retries=3)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"임시 폴더 정리 완료: {temp_dir}")

@celery_app.task(bind=True)
def process_audio_demucs_task(self, youtube_url: str):
    logger.info("process_audio_demucs_task 시작")
    temp_dir = tempfile.mkdtemp()
    logger.info(f"임시 폴더 생성됨: {temp_dir}")

    try:
        input_path = download_audio(youtube_url, temp_dir)
        logger.info(f"다운로드 완료: {input_path}")

        parts = separate_audio_demucs(input_path, temp_dir)
        logger.info("Demucs 분리 완료")

        vocal_name = generate_unique_filename("demucs_vocals")
        drums_name = generate_unique_filename("demucs_drums")
        bass_name = generate_unique_filename("demucs_bass")
        other_name = generate_unique_filename("demucs_other")

        vocal_final = os.path.join(temp_dir, vocal_name)
        drums_final = os.path.join(temp_dir, drums_name)
        bass_final = os.path.join(temp_dir, bass_name)
        other_final = os.path.join(temp_dir, other_name)

        shutil.copyfile(parts["vocals"], vocal_final)
        shutil.copyfile(parts["drums"], drums_final)
        shutil.copyfile(parts["bass"], bass_final)
        shutil.copyfile(parts["other"], other_final)

        vocal_url = upload_with_deletion("demucs-bucket", vocal_final, vocal_name)
        drums_url = upload_with_deletion("demucs-bucket", drums_final, drums_name)
        bass_url = upload_with_deletion("demucs-bucket", bass_final, bass_name)
        other_url = upload_with_deletion("demucs-bucket", other_final, other_name)

        return {
            "vocal_url": vocal_url,
            "drums_url": drums_url,
            "bass_url": bass_url,
            "other_url": other_url
        }

    except Exception as e:
        logger.error("예외 발생:")
        import traceback
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10, max_retries=3)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"임시 폴더 정리 완료: {temp_dir}")

@celery_app.task(bind=True)
def midi_conversion_task(self, file_bytes: bytes):
    logger.info("MIDI 변환 작업 시작")
    temp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(temp_dir, "input.wav")
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        y, sr = librosa.load(input_path, sr=None)
        duration = librosa.get_duration(y=y, sr=sr)

        if duration > 360:
            logger.error(f"WAV 파일 길이 초과: {duration:.2f}초")
            raise ValueError("업로드한 WAV 파일이 6분(360초)을 초과합니다.")

        output_name = generate_unique_filename("midi", ext="mid")
        output_path, bpm = convert_to_midi(file_bytes, temp_dir, output_name)

        midi_url = upload_with_deletion("midi-bucket", output_path, output_name)
        logger.info(f"MIDI 업로드 및 삭제 예약 완료 - URL: {midi_url}")

        pdf_name = output_name.replace(".mid", ".pdf")
        pdf_path = os.path.join(temp_dir, pdf_name)
        convert_midi_to_pdf(output_path, pdf_path)
        sheet_url = upload_with_deletion("sheet-bucket", pdf_path, pdf_name)

        return {
            "midi_url": midi_url,
            "bpm": bpm,
            "sheet_url": sheet_url
        }

    except Exception as e:
        logger.error("MIDI 변환 실패")
        import traceback
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10, max_retries=3)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"임시 폴더 정리 완료: {temp_dir}")
