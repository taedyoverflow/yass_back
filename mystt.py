import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

ALLOWED_STT_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".webm",
    ".flac",
    ".mp4",
    ".3gp",
    ".amr",
    ".caf",
    ".opus",
}

ALLOWED_MODEL_SIZES = {"turbo", "medium"}
ALLOWED_MODES = {"verbatim", "intended"}
ALLOWED_LANGUAGES = {"ko", "en", "auto"}

# 최대 2시간
MAX_STT_DURATION_SEC = 7200
# 스테레오 WAV 2시간 규모까지 허용
MAX_STT_UPLOAD_BYTES = 1600 * 1024 * 1024

_STT_SCRIPT = r"""
import json
import sys

from crisperwhisper import CrisperWhisperModel

audio_path, language, mode, model_size, out_json = sys.argv[1:6]

kwargs = {
    "mode": mode,
    "longform_strategy": "continuation",
}
if language and language != "auto":
    kwargs["language"] = language

model = CrisperWhisperModel(model_size, backend="transformers")
result = model.transcribe(audio_path, **kwargs)

text = (getattr(result, "text", None) or "").strip()
with open(out_json, "w", encoding="utf-8") as f:
    json.dump({"text": text}, f, ensure_ascii=False)
"""


def is_allowed_stt_filename(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_STT_EXTENSIONS


def get_audio_duration_seconds(file_path: str) -> float:
    """ffprobe 우선, 실패 시 librosa로 길이 측정."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        logger.warning("ffprobe 길이 측정 실패: %s", e)

    import librosa

    return float(librosa.get_duration(path=file_path))


def run_stt_task(
    audio_path: str,
    output_txt_path: str,
    language: str = "ko",
    mode: str = "intended",
    model_size: str = "turbo",
    timeout: int = 21600,
) -> str:
    """
    CrisperWhisper 2.0으로 전사. TF(Spleeter 등)와 충돌을 피하기 위해 별도 프로세스에서 실행.
    반환: 끊김 없이 이어진 전체 텍스트
    """
    if model_size not in ALLOWED_MODEL_SIZES:
        raise ValueError(f"지원하지 않는 모델 크기입니다: {model_size}")
    if mode not in ALLOWED_MODES:
        raise ValueError(f"지원하지 않는 mode입니다: {mode}")
    if language not in ALLOWED_LANGUAGES:
        raise ValueError(f"지원하지 않는 언어입니다: {language}")

    out_json = output_txt_path + ".json"
    logger.info(
        "STT subprocess 시작: model=%s language=%s mode=%s file=%s",
        model_size,
        language,
        mode,
        audio_path,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _STT_SCRIPT,
            audio_path,
            language,
            mode,
            model_size,
            out_json,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        logger.error("STT stderr: %s", result.stderr)
        logger.error("STT stdout: %s", result.stdout)
        raise RuntimeError(result.stderr.strip() or "STT 변환에 실패했습니다.")

    with open(out_json, "r", encoding="utf-8") as f:
        payload = json.load(f)

    text = (payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("전사 결과가 비어 있습니다.")

    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info("STT 완료: %d chars -> %s", len(text), output_txt_path)
    return text
