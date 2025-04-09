import tempfile
import time
import streamlit as st
import os
import subprocess


def run_infer_script(f0up_key, filter_radius, index_rate, rms_mix_rate, protect, hop_length, f0method, input_path, output_path, pth_path, index_path, split_audio, f0autotune, clean_audio, clean_strength, export_format):
    st.text("목소리 변환 중...")
    start_time = time.time()
    infer_script_path = "C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\rvc\\infer\\infer.py"
    command = [
        "python", infer_script_path,
        str(f0up_key),  # 문자열로 변환
        str(filter_radius),  # 필요하다면 문자열로 변환
        str(index_rate),
        str(hop_length),  # 문자열로 변환
        f0method,
        input_path,
        output_path,
        pth_path,
        index_path,
        str(split_audio),  # 필요하다면 문자열로 변환
        str(f0autotune),  # 필요하다면 문자열로 변환
        str(rms_mix_rate),
        str(protect),
        str(clean_audio),  # 필요하다면 문자열로 변환
        str(clean_strength),
        export_format,
    ]
    result = subprocess.run(command, capture_output=True, text=True)

    end_time = time.time()
    
    if result.returncode == 0:
        st.text(f"목소리 변환 완료, 총 소요 시간: {end_time - start_time:.2f}초")
        if os.path.exists(output_path):
            st.success("파일 변환에 성공했습니다!")
            return output_path  # 성공한 경우 변환된 파일의 경로를 반환
        else:
            st.error(f"파일 변환은 성공했으나 {output_path} 파일을 찾을 수 없습니다.")
    else:
        st.error(f"오류 발생: {result.stderr}")
        print(f"오류 발생: {result.stderr}")
    
    return None  # 실패한 경우 None 반환

def mix_audio(vocal_path, accompaniment_path, output_path):
    st.text("보컬과 반주를 합성 중...")
    start_time = time.time()  # 합성 시작 시간

    # `ffmpeg` 명령어 실행
    command = [
    "ffmpeg",
    "-i", vocal_path,
    "-i", accompaniment_path,
    "-filter_complex", "amix=inputs=2:duration=longest",
    output_path
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(f"보컬과 반주 합성에 성공했습니다! 소요 시간: {time.time() - start_time:.2f}초")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"보컬과 반주 합성에 실패했습니다: {e.stderr}")
        return None


def main():
    st.title("음성 변환 도구")

    input_audio = st.file_uploader("보컬 입력 파일 선택:", type=['wav', 'mp3'])

    converted_file_path = None

    if input_audio is not None:
        pth_file = st.selectbox("PTH 파일 선택:", os.listdir("C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\pth"))
        # 'None' 옵션을 포함해 인덱스 파일 선택
        index_options = ["None"] + os.listdir("C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\index")
        index_file = st.selectbox("Index 파일 선택 (선택사항):", index_options)
        index_rate = st.slider("Index 비율:", min_value=0.0, max_value=1.0, value=0.7, step=0.01)
        f0up_key = st.slider("피치 입력: (남자모델->여자노래=-2~-4 / 여자모델->남자노래=2~4)", min_value=-24, max_value=24, value=0)

        filter_radius = "3"
        rms_mix_rate = "1.0"
        protect = "0.33"
        hop_length = "128"
        f0method = "rmvpe"
        split_audio = "False"
        f0autotune = "False"
        clean_audio = "False"
        clean_strength = "0.7"
        export_format = "WAV"

        if st.button("변환"):
            input_audio_name = input_audio.name
            output_dir = "opt_infer"
            os.makedirs(output_dir, exist_ok=True)
            vocal_output_path = os.path.join(output_dir, f"{input_audio_name}_converted_vocal.wav")  # 변환된 보컬 파일 경로
            final_output_path = os.path.join(output_dir, f"{input_audio_name}_mix_audio.wav")  # 최종 합성 파일 경로

            with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
                temp_audio_path = temp_audio.name
                temp_audio.write(input_audio.getvalue())

            converted_file_path = run_infer_script(
                f0up_key, filter_radius, index_rate, rms_mix_rate, protect, hop_length,
                f0method, temp_audio_path, vocal_output_path, os.path.join("C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\pth", pth_file),
                os.path.join("C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\index", index_file), split_audio, f0autotune,
                clean_audio, clean_strength, export_format
            )

            if converted_file_path:
                # 파일명에서 기본 이름 추출 (확장자 제외)
                base_name = os.path.splitext(os.path.basename(input_audio_name))[0].replace("_vocals", "")
                # 반주 파일 경로 생성
                accompaniment_path = os.path.join("C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\static\\opt_spleeter", f"{base_name}_accompaniment.wav")

                final_mix_path = mix_audio(converted_file_path, accompaniment_path, final_output_path)

                if final_mix_path:
                    st.audio(final_mix_path)
                else:
                    st.error("최종 합성 파일 생성 실패")
            else:
                st.write("보컬 입력 파일을 업로드해주세요.")


if __name__ == "__main__":
    main()