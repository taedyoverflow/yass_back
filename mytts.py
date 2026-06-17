from gtts import gTTS
import re

def run_tts_task(text: str, voice: str, output_path: str):
    try:
        # 텍스트에 한글이 있는지 확인하여 언어 자동 감지
        has_korean = bool(re.search(r'[가-힣]', text))
        lang = 'ko' if has_korean else 'en'
        
        # gTTS로 음성 생성
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(output_path)

        print(f"TTS 저장 완료: {output_path}")
    except Exception as e:
        print(f"TTS 생성 중 오류 발생: {e}")
        raise