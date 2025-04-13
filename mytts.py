import edge_tts
import asyncio

def run_tts_task(text: str, voice: str, output_path: str):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        communicate = edge_tts.Communicate(text, voice)
        loop.run_until_complete(communicate.save(output_path))
        loop.close()
        print(f"✅ TTS 저장 완료: {output_path}")
    except Exception as e:
        print(f"❌ TTS 생성 중 오류 발생: {e}")
        raise
