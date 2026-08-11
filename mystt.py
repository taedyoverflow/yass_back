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

ALLOWED_MODEL_SIZES = {"small", "turbo", "medium"}
ALLOWED_MODES = {"verbatim", "intended"}
ALLOWED_LANGUAGES = {"ko", "en", "auto"}

# 최대 2시간
MAX_STT_DURATION_SEC = 7200
# 스테레오 WAV 2시간 규모까지 허용
MAX_STT_UPLOAD_BYTES = 1600 * 1024 * 1024

# 메인 venv(celery/spleeter/gTTS)와 click 등이 충돌하므로 STT는 별도 venv 권장.
# 우선순위: STT_PYTHON 환경변수 → ./venv_stt/bin/python → 현재 인터프리터
def get_stt_python() -> str:
    env_python = os.environ.get("STT_PYTHON", "").strip()
    if env_python and os.path.isfile(env_python):
        return env_python

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "venv_stt", "bin", "python"),
        os.path.join(base_dir, "venv_stt", "Scripts", "python.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    return sys.executable


def preprocess_audio_for_stt(input_path: str, output_path: str) -> str:
    """
    STT용 전처리: 16kHz / mono / 음성에 충분한 비트레이트.
    Whisper는 내부적으로 16kHz를 쓰므로 품질 손실이 거의 없고,
    디코딩·전송·로딩은 가벼워진다.
    (주의: 추론 시간은 파일 용량이 아니라 오디오 '길이(초)'에 비례한다.)
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "48k",
        output_path,
    ]
    logger.info("STT 전처리 시작: %s -> %s", input_path, output_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not os.path.isfile(output_path):
        logger.error("STT 전처리 실패: %s", result.stderr)
        raise RuntimeError(result.stderr.strip() or "오디오 전처리에 실패했습니다.")

    in_size = os.path.getsize(input_path)
    out_size = os.path.getsize(output_path)
    logger.info(
        "STT 전처리 완료: %dKB -> %dKB (16kHz mono mp3)",
        in_size // 1024,
        out_size // 1024,
    )
    return output_path


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

# ct2(+int8)가 훨씬 빠름. 실패 시 transformers로 폴백.
model = None
last_error = None
for backend, extra in (
    ("ct2", {"compute_type": "int8"}),
    ("transformers", {}),
):
    try:
        model = CrisperWhisperModel(model_size, backend=backend, **extra)
        print(f"[stt] backend={backend}", flush=True)
        break
    except Exception as exc:
        last_error = exc
        print(f"[stt] backend={backend} failed: {exc}", flush=True)

if model is None:
    raise RuntimeError(f"STT 모델 로드 실패: {last_error}")

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
    model_size: str = "small",
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

    work_dir = os.path.dirname(output_txt_path) or "."
    preprocessed_path = os.path.join(work_dir, "stt_16k_mono.mp3")
    try:
        preprocess_audio_for_stt(audio_path, preprocessed_path)
        stt_input = preprocessed_path
    except Exception as e:
        logger.warning("전처리 실패, 원본으로 진행: %s", e)
        stt_input = audio_path

    out_json = output_txt_path + ".json"
    stt_python = get_stt_python()
    logger.info(
        "STT subprocess 시작: python=%s model=%s language=%s mode=%s file=%s",
        stt_python,
        model_size,
        language,
        mode,
        stt_input,
    )

    result = subprocess.run(
        [
            stt_python,
            "-c",
            _STT_SCRIPT,
            stt_input,
            language,
            mode,
            model_size,
            out_json,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.stdout:
        logger.info("STT stdout: %s", result.stdout.strip())
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
