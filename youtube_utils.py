import subprocess
import json

YTDLP_CMD = [
    "/usr/bin/sudo", "-u", "user1",
    "/home/user1/.local/bin/yt-dlp",
    "--cookies-from-browser", "chrome"
]

def get_video_duration(url: str) -> int:
    command = YTDLP_CMD + ["--skip-download", "--print-json", url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)

        duration = info.get("duration")
        if duration is None:
            print("⚠️ duration 필드가 존재하지 않음")
            return -1  # duration 없는 경우 특별 처리
        return duration

    except Exception as e:
        print(f"❌ duration 추출 중 오류: {e}")
        return -1  # 오류 시도 -1 처리

def validate_youtube_exists(url: str) -> bool:
    command = YTDLP_CMD + ["--skip-download", "--print-json", url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        return "duration" in info
    except Exception as e:
        print(f"❌ 존재 여부 확인 실패: {e}")
        return False