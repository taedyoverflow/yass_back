import logging
import os
import subprocess
import sys

import librosa
import numpy as np

logger = logging.getLogger(__name__)

_PREDICT_SCRIPT = """
from basic_pitch.inference import predict
import sys

input_path, output_path = sys.argv[1], sys.argv[2]
_, midi_data, _ = predict(input_path)
midi_data.write(output_path)
"""


def _run_basic_pitch_subprocess(input_path: str, output_path: str, timeout: int = 300) -> None:
    """Spleeter 등과 TF 그래프 충돌을 피하기 위해 별도 프로세스에서 Basic Pitch 실행."""
    logger.info("[basic_pitch] subprocess 시작: %s", input_path)
    result = subprocess.run(
        [sys.executable, "-c", _PREDICT_SCRIPT, input_path, output_path],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"Basic Pitch 변환 실패: {stderr}")

    if not os.path.isfile(output_path):
        raise RuntimeError("Basic Pitch subprocess가 MIDI 파일을 생성하지 않았습니다.")

    logger.info("[basic_pitch] subprocess 완료: %s", output_path)


def convert_to_midi(file_bytes: bytes, output_dir: str, output_filename: str) -> tuple:
    input_path = os.path.join(output_dir, "input.wav")
    with open(input_path, "wb") as f:
        f.write(file_bytes)

    y, sr = librosa.load(input_path)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

    if isinstance(tempo, (list, np.ndarray)):
        bpm = float(tempo[0]) if len(tempo) > 0 else 0
    else:
        bpm = float(tempo)

    output_path = os.path.join(output_dir, output_filename)
    _run_basic_pitch_subprocess(input_path, output_path)

    return output_path, round(bpm)


def convert_midi_to_pdf(midi_path: str, pdf_path: str):
    musescore_path = "/usr/bin/musescore"
    result = subprocess.run(
        ["xvfb-run", "-a", musescore_path, midi_path, "-o", pdf_path],
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"MuseScore PDF 변환 실패: {result.stderr.decode()}")
