import os
import subprocess
from spleeter.separator import Separator

def download_audio(youtube_url: str, temp_dir: str) -> str:
    print(f"🎬 [download_audio] 다운로드 대상 URL: {youtube_url}")
    output_path = os.path.join(temp_dir, "input.%(ext)s")

    print("💻 서버 환경")
    command = [
    "/usr/bin/sudo", "-u", "user1",
    "/home/user1/.local/bin/yt-dlp",
    "--cookies-from-browser", "chrome",
    "-x", "--audio-format", "mp3",
    "-o", output_path,
    youtube_url
    ]


    print(f"⚙️ [download_audio] yt-dlp 명령어: {' '.join(command)}")

    try:
        subprocess.run(command, check=True, timeout=30)
        print("✅ [download_audio] yt-dlp 명령어 실행 완료")
    except subprocess.TimeoutExpired:
        print("⏱️ [download_audio] yt-dlp 타임아웃: 30초 내에 완료되지 않음")
        raise
    except Exception as e:
        print(f"❌ [download_audio] yt-dlp 실행 중 오류 발생: {e}")
        raise

    for file in os.listdir(temp_dir):
        if file.endswith(".mp3"):
            final_path = os.path.join(temp_dir, file)
            print(f"✅ [download_audio] MP3 파일 발견: {final_path}")
            return final_path

    raise FileNotFoundError("❌ [download_audio] MP3 파일을 찾을 수 없습니다.")


def separate_audio(audio_path: str, temp_dir: str) -> tuple[str, str]:
    print("🎧 [separate_audio] Spleeter 분리 시작")
    separator = Separator('spleeter:2stems')
    separator.separate_to_file(audio_path, temp_dir, codec="wav")

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_dir = os.path.join(temp_dir, base_name)

    vocals_path = os.path.join(output_dir, "vocals.wav")
    accompaniment_path = os.path.join(output_dir, "accompaniment.wav")

    print(f"✅ [separate_audio] 분리 완료: vocals={vocals_path}, accomp={accompaniment_path}")
    return vocals_path, accompaniment_path
