import subprocess
import json

YTDLP_BIN = "/home/user1/yass_back/venv/bin/yt-dlp"
YTDLP_USER = "user1"
YTDLP_ENV_PATH = "/home/user1/.deno/bin:/usr/local/bin:/usr/bin:/bin"


def build_ytdlp_command(*args: str) -> list[str]:
    return [
        "/usr/bin/sudo", "-u", YTDLP_USER,
        "env", f"PATH={YTDLP_ENV_PATH}",
        YTDLP_BIN,
        "--cookies-from-browser", "chrome",
        *args,
    ]


def get_video_duration(url: str) -> int:
    command = build_ytdlp_command("--skip-download", "--print-json", url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)

        duration = info.get("duration")
        if duration is None:
            print("duration 필드가 존재하지 않음")
            return -1
        return duration

    except Exception as e:
        print(f"duration 추출 중 오류: {e}")
        return -1


def validate_youtube_exists(url: str) -> bool:
    command = build_ytdlp_command("--skip-download", "--print-json", url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        return "duration" in info
    except Exception as e:
        print(f"존재 여부 확인 실패: {e}")
        return False
