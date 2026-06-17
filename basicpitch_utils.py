import os
import librosa
import numpy as np
from basic_pitch.inference import predict
import subprocess
import threading

# 락 추가 (TensorFlow Graph 충돌 방지용)
_basic_pitch_lock = threading.Lock()

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

    with _basic_pitch_lock:
        _, midi_data, _ = predict(input_path)

    output_path = os.path.join(output_dir, output_filename)
    midi_data.write(output_path)

    return output_path, round(bpm)

def convert_midi_to_pdf(midi_path: str, pdf_path: str):
    musescore_path = "/usr/bin/musescore"
    result = subprocess.run(["xvfb-run", "-a", musescore_path, midi_path, "-o", pdf_path], capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(f"MuseScore PDF 변환 실패: {result.stderr.decode()}")
