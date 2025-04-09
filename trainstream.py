import time
import streamlit as st
import os
import subprocess
from rvc.configs.config import Config

from rvc.train.extract.preparing_files import generate_config, generate_filelist
from rvc.lib.tools.pretrained_selector import pretrained_selector


config = Config()
current_script_directory = os.path.dirname(os.path.realpath(__file__))
logs_path = os.path.join(current_script_directory, "logs")

# Preprocess
def run_preprocess_script(model_name, dataset_path, sampling_rate):
    per = 3.0 if config.is_half else 3.7
    preprocess_script_path = os.path.join("rvc", "train", "preprocess", "preprocess.py")
    command = [
        "python",
        preprocess_script_path,
        *map(
            str,
            [
                os.path.join(logs_path, model_name),
                dataset_path,
                sampling_rate,
                per,
            ],
        ),
    ]

    os.makedirs(os.path.join(logs_path, model_name), exist_ok=True)
    try:
        subprocess.run(command, check=True)
        return f"Model {model_name} preprocessed successfully."
    except subprocess.CalledProcessError as e:
        return f"Error in preprocessing model {model_name}: {e}"

# Extract
def run_extract_script(model_name, rvc_version, f0method, hop_length, sampling_rate):
    model_path = os.path.join(logs_path, model_name)
    extract_f0_script_path = os.path.join(
        "rvc", "train", "extract", "extract_f0_print.py"
    )
    extract_feature_script_path = os.path.join(
        "rvc", "train", "extract", "extract_feature_print.py"
    )

    command_1 = [
        "python",
        extract_f0_script_path,
        *map(
            str,
            [
                model_path,
                f0method,
                hop_length,
            ],
        ),
    ]
    command_2 = [
        "python",
        extract_feature_script_path,
        *map(
            str,
            [
                config.device,
                "1",
                "0",
                "0",
                model_path,
                rvc_version,
                "True",
            ],
        ),
    ]
    try:
        subprocess.run(command_1, check=True)
        subprocess.run(command_2, check=True)
        generate_config(rvc_version, sampling_rate, model_path)
        generate_filelist(f0method, model_path, rvc_version, sampling_rate)
        return f"Model {model_name} extracted successfully."
    except subprocess.CalledProcessError as e:
        return f"Error in extracting features for model {model_name}: {e}"

# Train
def run_train_script(
    model_name,
    rvc_version,
    save_every_epoch,
    save_only_latest,
    save_every_weights,
    total_epoch,
    sampling_rate,
    batch_size,
    gpu,
    pitch_guidance,
    pretrained,
    custom_pretrained,
    g_pretrained_path=None,
    d_pretrained_path=None,
):
    f0 = 1 if str(pitch_guidance) == "True" else 0
    latest = 1 if str(save_only_latest) == "True" else 0
    save_every = 1 if str(save_every_weights) == "True" else 0

    if str(pretrained) == "True":
        if str(custom_pretrained) == "False":
            pg, pd = pretrained_selector(f0)[rvc_version][sampling_rate]
        else:
            if g_pretrained_path is None or d_pretrained_path is None:
                raise ValueError(
                    "Please provide the path to the pretrained G and D models."
                )
            pg, pd = g_pretrained_path, d_pretrained_path
    else:
        pg, pd = "", ""

    train_script_path = os.path.join("rvc", "train", "train.py")
    command = [
        "python",
        train_script_path,
        *map(
            str,
            [
                "-se",
                save_every_epoch,
                "-te",
                total_epoch,
                "-pg",
                pg,
                "-pd",
                pd,
                "-sr",
                sampling_rate,
                "-bs",
                batch_size,
                "-g",
                gpu,
                "-e",
                os.path.join(logs_path, model_name),
                "-v",
                rvc_version,
                "-l",
                latest,
                "-c",
                "0",
                "-sw",
                save_every,
                "-f0",
                f0,
            ],
        ),
    ]

    try:
        subprocess.run(command, check=True)
        return f"Model {model_name} trained successfully."
    except subprocess.CalledProcessError as e:
        return f"Error in training model {model_name}: {e}"

# Index
def run_index_script(model_name, rvc_version):
    index_script_path = os.path.join("rvc", "train", "process", "extract_index.py")
    command = [
        "python",
        index_script_path,
        os.path.join(logs_path, model_name),
        rvc_version,
    ]

    try:
        subprocess.run(command, check=True)
        return f"Index file for {model_name} generated successfully."
    except subprocess.CalledProcessError as e:
        return f"Error in generating index file for model {model_name}: {e}"

# 스트림릿 페이지 설정
st.title("RVC CLI Voice Conversion")

# 모델 이름 입력 받기
model_name = st.text_input("Please enter a model name:", "default_model_name")

# 디렉토리 경로 직접 설정
recording_dir = "C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\static\\recordings"
dataset_path = recording_dir

# 필요한 설정 값 정의
sampling_rate = "48000"  # 샘플링 레이트
rvc_version = "v2"  # RVC 모델 버전
f0method = "rmvpe"  # 피치 추출 알고리즘
hop_length = 128  # 홉 길이
total_epoch = 500  # 총 에폭 수
batch_size = 8  # 배치 크기
gpu = "0"  # 사용할 GPU 번호
pitch_guidance = True  # 피치 유도 사용 여부
pretrained = True  # 사전 훈련된 모델 사용 여부
custom_pretrained = False  # 사용자 정의 사전 훈련 모델 사용 여부

if st.button("Start Training"):
    try:
        # 전처리 시작 시간
        start_time = time.time()
        preprocess_status = run_preprocess_script(model_name, dataset_path, sampling_rate)
        st.write(preprocess_status)
        # 전처리 소요 시간
        st.write(f"Preprocessing took {time.time() - start_time:.2f} seconds.")

        # 특성 추출 시작 시간
        start_time = time.time()
        extract_status = run_extract_script(model_name, rvc_version, f0method, hop_length, sampling_rate)
        st.write(extract_status)
        # 특성 추출 소요 시간
        st.write(f"Feature extraction took {time.time() - start_time:.2f} seconds.")

        # 모델 훈련 시작 시간
        start_time = time.time()
        train_status = run_train_script(model_name, rvc_version, 10, False, True, total_epoch, sampling_rate, batch_size, gpu, pitch_guidance, pretrained, custom_pretrained)
        st.write(train_status)
        # 모델 훈련 소요 시간
        st.write(f"Training took {time.time() - start_time:.2f} seconds.")

        # 인덱스 파일 생성 시작 시간
        start_time = time.time()
        index_status = run_index_script(model_name, rvc_version)
        st.write(index_status)
        # 인덱스 파일 생성 소요 시간
        st.write(f"Index file creation took {time.time() - start_time:.2f} seconds.")
    
    except Exception as e:
        # 예외 발생 시 사용자에게 알림
        st.error(f"An error occurred during the process: {str(e)}")