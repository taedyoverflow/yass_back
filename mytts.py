import edge_tts
import asyncio

def run_tts_task(text: str, voice: str, output_path: str):
    try:
        async def do_tts():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(do_tts())
        loop.run_until_complete(asyncio.sleep(0.5))
        loop.close()

        print(f"TTS 저장 완료: {output_path}")
    except Exception as e:
        print(f"TTS 생성 중 오류 발생: {e}")
        raise