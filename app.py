import os
import asyncio
import tempfile
import shutil
import subprocess
import threading
import time
from typing import Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from spleeter.separator import Separator

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class YoutubeURL(BaseModel):
    url: str

# 유튜브 오디오 다운로드
def download_audio_temp(youtube_url: str, temp_dir: str) -> str:
    file_name = "input.mp3"
    output_path = os.path.join(temp_dir, file_name)
    command = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "-o", output_path,
        youtube_url
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output_path
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Audio download failed: {e.stderr.decode()}")

async def spleeter_separate(audio_path: str, temp_dir: str) -> Tuple[str, str]:
    # 요청마다 새로 생성
    separator = Separator('spleeter:2stems')
    await asyncio.to_thread(separator.separate_to_file, audio_path, temp_dir, codec="wav")

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    vocal_path = os.path.join(temp_dir, base_name, "vocals.wav")
    accompaniment_path = os.path.join(temp_dir, base_name, "accompaniment.wav")

    if not (os.path.exists(vocal_path) and os.path.exists(accompaniment_path)):
        raise HTTPException(status_code=500, detail="Separated files not found.")

    return vocal_path, accompaniment_path


# 중복 삭제 방지를 위한 집합과 락
deleted_dirs = set()
lock = threading.Lock()

# 중복 방지 안전 삭제 함수
def safe_cleanup(cleanup_dir: str):
    with lock:
        if cleanup_dir in deleted_dirs:
            return
        deleted_dirs.add(cleanup_dir)
    
    time.sleep(60)  # 1분 대기 후 삭제
    print(f"[CLEANUP] Deleting temp dir: {cleanup_dir}")
    shutil.rmtree(cleanup_dir, ignore_errors=True)

# 비동기 스트리밍 제너레이터
async def async_stream_file_and_cleanup(file_path: str, cleanup_dir: str):
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):  # 1MB 단위 스트리밍
                yield chunk
    finally:
        threading.Thread(target=safe_cleanup, args=(cleanup_dir,)).start()



# POST: 오디오 처리 요청
@app.post("/process_audio/")
async def process_audio(youtube: YoutubeURL):
    temp_dir = tempfile.mkdtemp()
    try:
        input_audio = await asyncio.get_event_loop().run_in_executor(None, download_audio_temp, youtube.url, temp_dir)
        vocal_path, accompaniment_path = await spleeter_separate(input_audio, temp_dir)

        base_name = os.path.splitext(os.path.basename(input_audio))[0]

        return {
            "vocal_stream_url": f"/stream/vocal/{os.path.basename(temp_dir)}/{base_name}",
            "accompaniment_stream_url": f"/stream/accompaniment/{os.path.basename(temp_dir)}/{base_name}"
        }
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

# GET: 스트리밍 라우트
@app.get("/stream/{track_type}/{temp_id}/{base_name}")
async def stream_audio(track_type: str, temp_id: str, base_name: str):
    filename_map = {
        "vocal": "vocals.wav",
        "accompaniment": "accompaniment.wav"
    }

    if track_type not in filename_map:
        raise HTTPException(status_code=400, detail="Invalid track type")

    temp_base = os.path.join(tempfile.gettempdir(), temp_id)
    file_path = os.path.join(temp_base, base_name, filename_map[track_type])

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    return StreamingResponse(
    async_stream_file_and_cleanup(file_path, temp_base),
    media_type="audio/wav"
)




# # 로깅 설정
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # 모든 도메인에서 오는 요청을 허용합니다. 보안을 위해 배포 시에는 특정 도메인으로 제한하세요.
#     allow_credentials=True,
#     allow_methods=["*"],  # 모든 HTTP 메소드를 허용합니다.
#     allow_headers=["*"],  # 모든 HTTP 헤더를 허용합니다.
# )

# # 다운로드 및 스트리밍을 위한 정적 파일 디렉토리 설정
# app.mount("/static", StaticFiles(directory="static/opt_spleeter"), name="static")

# # SEPARATION
# # SEPARATION
# # SEPARATION
# # SEPARATION
# # SEPARATION
# class SearchQuery(BaseModel):
#     query: str

# # API 키와 YouTube API 서비스 객체를 설정합니다.
# YOUTUBE_API_KEY = ''
# youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# @app.post("/youtube_search/")
# async def youtube_search(search_query: SearchQuery):
#     try:
#         # YouTube API를 사용하여 검색을 수행합니다.
#         request = youtube.search().list(
#             q=search_query.query,
#             part="snippet",
#             type="video",
#             maxResults=10
#         )
#         response = request.execute()

#         # 검색 결과를 처리하고 반환합니다.
#         videos = []
#         for item in response['items']:
#             thumbnail_url = item['snippet']['thumbnails']['high']['url']
#             video_link = f"https://www.youtube.com/watch?v={item['id']['videoId']}"
#             videos.append({
#                 'title': item['snippet']['title'],
#                 'description': item['snippet']['description'],
#                 'videoId': item['id']['videoId'],
#                 'link': video_link,  # 여기에 비디오 링크를 추가, 누락된 콤마 추가
#                 'thumbnail': thumbnail_url  # 썸네일 URL을 비디오 정보에 추가
#             })

#         return {'videos': videos}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    
# @app.post("/youtube_search/")
# async def youtube_search(search_query: SearchQuery):
#     try:
#         # YouTube API를 사용하여 검색을 수행합니다.
#         request = youtube.search().list(
#             q=search_query.query,
#             part="snippet",
#             type="video",
#             maxResults=10
#         )
#         response = request.execute()

#         # 검색 결과를 처리하고 반환합니다.
#         videos = []
#         for item in response['items']:
#             thumbnail_url = item['snippet']['thumbnails']['high']['url']
#             video_link = f"https://www.youtube.com/watch?v={item['id']['videoId']}"
#             videos.append({
#                 'title': item['snippet']['title'],
#                 'description': item['snippet']['description'],
#                 'videoId': item['id']['videoId'],
#                 'link': video_link,  # 여기에 비디오 링크를 추가, 누락된 콤마 추가
#                 'thumbnail': thumbnail_url  # 썸네일 URL을 비디오 정보에 추가
#             })

#         return {'videos': videos}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # 비동기 실행을 위한 동기 함수
# def download_audio_sync(youtube_url: str, output_path: str) -> str:
#     os.makedirs(output_path, exist_ok=True)
#     file_hash = hashlib.md5(youtube_url.encode('utf-8')).hexdigest()
#     file_name = f"{file_hash}.mp3"
#     command = f'yt-dlp -x --audio-format mp3 -o "{output_path}/{file_name}" {youtube_url}'

#     try:
#         # subprocess.run 대신 사용
#         result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         return os.path.join(output_path, file_name)
#     except subprocess.CalledProcessError as e:
#         raise HTTPException(status_code=500, detail=f"Audio download failed: {e.stderr.decode()}")

# # 비동기 래퍼 함수
# async def download_audio(youtube_url: str, output_path: str) -> str:
#     loop = asyncio.get_running_loop()
#     return await loop.run_in_executor(
#         None,  # 기본 executor 사용
#         download_audio_sync,  # 실행할 함수
#         youtube_url,  # 함수의 첫 번째 인자
#         output_path  # 함수의 두 번째 인자
#     )

# async def spleeter_process_async(audio_path: str, output_dir: str) -> Tuple[str, str]:
#     from spleeter.separator import Separator  # spleeter는 여기서 임포트하는 것이 좋습니다 (스레드 이슈 방지)
    
#     separator = Separator('spleeter:2stems')
#     base_name = os.path.basename(audio_path).split('.')[0]
    
#     # spleeter 분리 작업을 별도의 스레드에서 비동기적으로 실행
#     await asyncio.to_thread(separator.separate_to_file, audio_path, output_dir, filename_format=f"{base_name}_{{instrument}}.{{codec}}")
    
#     vocal_path = os.path.join(output_dir, f'{base_name}_vocals.wav')
#     accompaniment_path = os.path.join(output_dir, f'{base_name}_accompaniment.wav')
#     return vocal_path, accompaniment_path

# class YoutubeURL(BaseModel):
#     url: str

# @app.post("/process_audio/")
# async def process_audio(youtube_url: YoutubeURL):
#     # 'static' 폴더 내에 저장될 디렉토리 경로를 지정합니다.
#     output_path_download = "static/opt_youtube"  # 수정된 경로
#     output_dir_spleeter = "static/opt_spleeter"  # 수정된 경로
    
#     # 필요에 따라 'static/opt_youtube'와 'static/opt_spleeter' 디렉토리를 생성합니다.
#     os.makedirs(output_path_download, exist_ok=True)
#     os.makedirs(output_dir_spleeter, exist_ok=True)
    
#     downloaded_audio_path = await download_audio(youtube_url.url, output_path_download)
#     vocal_path, accompaniment_path = await spleeter_process_async(downloaded_audio_path, output_dir_spleeter)
    
#     # 'static' URL 경로를 사용하여 스트리밍 및 다운로드 URL 생성
#     base_url = "http://192.168.0.187:8000/static"
#     vocal_stream_url = f"{base_url}/{os.path.basename(vocal_path)}"
#     accompaniment_stream_url = f"{base_url}/{os.path.basename(accompaniment_path)}"

#     return {
#         "vocal_stream_url": vocal_stream_url,
#         "accompaniment_stream_url": accompaniment_stream_url,
#         "vocal_download_url": f"/download/{os.path.basename(vocal_path)}",
#         "accompaniment_download_url": f"/download/{os.path.basename(accompaniment_path)}"
#     }

# @app.get("/download/{filename}", response_class=FileResponse)
# async def download_file(filename: str):
#     file_path = f"static/opt_spleeter/{filename}"  # 수정된 경로
#     if os.path.exists(file_path):
#         return FileResponse(path=file_path, filename=filename, media_type='audio/wav')
#     else:
#         raise HTTPException(status_code=404, detail="File not found")
    



# # INFERENCE
# # INFERENCE
# # INFERENCE
# # INFERENCE
# # INFERENCE
# def list_files(directory: str) -> List[str]:
#     return os.listdir(directory)

# @app.get("/list-pth-files/")
# async def list_pth_files():
#     pth_directory = "weights/pth"
#     return list_files(pth_directory)

# @app.get("/list-index-files/")
# async def list_index_files():
#     index_directory = "weights/index"
#     return list_files(index_directory)


# @app.get("/check-accompaniment/{filename}")
# async def check_accompaniment(filename: str):
#     # 반주 파일 경로 구성
#     accompaniment_path = f"static/opt_spleeter/{filename}_accompaniment.wav"
#     # 반주 파일 존재 여부 확인
#     if exists(accompaniment_path):
#         return {"exists": True}
#     else:
#         return {"exists": False}
    
# def run_infer_script(f0up_key, filter_radius, index_rate, rms_mix_rate, protect, hop_length, f0method, input_path, output_path, pth_path, index_path, split_audio, f0autotune, clean_audio, clean_strength, export_format):
#     infer_script_path = "C:\\Users\\user\\Desktop\\aifinal\\rvc\\infer\\infer.py"
#     command = [
#         "python", infer_script_path,
#         str(f0up_key),
#         str(filter_radius),
#         str(index_rate),
#         str(hop_length),
#         f0method,
#         input_path,
#         output_path,
#         pth_path,
#         index_path,
#         str(split_audio),
#         str(f0autotune),
#         str(rms_mix_rate),
#         str(protect),
#         str(clean_audio),
#         str(clean_strength),
#         export_format,
#     ]
#     logging.info("Running infer script with command: %s", command)
#     try:
#         result = subprocess.run(command, capture_output=True, text=True, check=True)
#         logging.info("Infer script output: %s", result.stdout)
#         if os.path.exists(output_path):
#             return {"status": "success", "output_path": output_path}
#         else:
#             logging.error("Output file not found after inference: %s", output_path)
#             return {"status": "error", "message": "Output file not found after inference."}
#     except subprocess.CalledProcessError as e:
#         logging.error("Infer script error: %s", e.stderr)  # 에러 메시지 로깅
#         logging.error("Infer script output: %s", e.stdout)  # 스크립트 실행 결과 로깅
#     return {"status": "error", "message": f"Infer script error: {e.stderr}"}
    
# async def async_run_infer(*args, **kwargs):
#     try:
#         result = await run_in_threadpool(run_infer_script, *args, **kwargs)
#         logging.info("Infer script completed with result: %s", result)
#         return result  # 성공 시 결과 반환
#     except Exception as e:
#         logging.exception("An error occurred during async inference: %s", e)
#         return {"status": "error", "message": str(e)}  # 오류 발생 시 오류 메시지 반환


# def mix_audio(vocal_path, accompaniment_path, output_path):
#     command = [
#         "ffmpeg",
#         "-i", vocal_path,
#         "-i", accompaniment_path,
#         "-filter_complex", "amix=inputs=2:duration=longest",
#         output_path
#     ]
#     logging.info("Running mix audio with command: %s", command)
#     try:
#         result = subprocess.run(command, capture_output=True, text=True, check=True)
#         logging.info("Mix audio output (stdout): %s", result.stdout)  # 표준 출력 로깅
#         logging.info("Mix audio output (stderr): %s", result.stderr)  # 표준 에러도 로깅
#         return output_path
#     except subprocess.CalledProcessError as e:
#         logging.error("Mix audio error (stderr): %s", e.stderr)  # 에러 발생 시 표준 에러 로깅
#         return {"status": "error", "message": f"Mix audio error: {e.stderr}"}

    
# async def async_mix_audio(*args, **kwargs):
#     try:
#         return await run_in_threadpool(mix_audio, *args, **kwargs)
#     except Exception as e:
#         logging.exception("An error occurred during async audio mixing.")
#         return {"status": "error", "message": str(e)}

# @app.post("/convert-audio/")
# async def convert_audio(input_audio: UploadFile = File(...), pth_file: str = Form(...), index_file: str = Form(None), index_rate: float = Form(...), f0up_key: int = Form(...), filter_radius: int = Form(...), rms_mix_rate: float = Form(...), protect: float = Form(...), hop_length: int = Form(...), f0method: str = Form(...), split_audio: bool = Form(...), f0autotune: bool = Form(...), clean_audio: bool = Form(...), clean_strength: float = Form(...), export_format: str = Form(...)):
#     # 파일 경로에서 파일 이름만 추출 (경로 제거)
#     file_name = os.path.basename(input_audio.filename)
#     # 파일 이름에서 확장자 제거
#     base_name, _ = os.path.splitext(file_name)
#     # 파일 이름에서 "_vocals" 부분 제거
#     base_name = base_name.replace("_vocals", "")

#     # 파일 시스템 작업에 대한 예외 처리 추가
#     try:
#         output_dir = "C:\\Users\\user\\Desktop\\aifinal\\static\\opt_infer"
#         os.makedirs(output_dir, exist_ok=True)
#     except Exception as e:
#         logging.exception("Failed to create or access the output directory.")
#         return {"error": "Failed to create or access the output directory.", "details": str(e)}

#     vocal_output_path = os.path.join(output_dir, f"{base_name}_converted_vocal.wav")
#     final_output_path = os.path.join(output_dir, f"{base_name}_mix_audio.wav")

#     # 임시 파일에 입력 오디오 파일 저장
#     try:
#         with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
#             temp_audio_path = temp_audio.name
#             contents = await input_audio.read()
#             temp_audio.write(contents)
#             temp_audio.flush()
#     except Exception as e:
#         logging.exception("Failed to create or write to the temporary audio file.")
#         return {"error": "Failed to create or write to the temporary audio file.", "details": str(e)}

#     # run_infer_script 실행
#     converted_file_result = await async_run_infer(f0up_key, filter_radius, index_rate, rms_mix_rate, protect, hop_length, f0method, temp_audio_path, vocal_output_path, os.path.join("C:\\Users\\user\\Desktop\\aifinal\\weights\\pth", pth_file), os.path.join("C:\\Users\\user\\Desktop\\aifinal\\weights\\index", index_file) if index_file else "", split_audio, f0autotune, clean_audio, clean_strength, export_format)

#     if converted_file_result and converted_file_result['status'] == 'success':
#         accompaniment_path = os.path.join("C:\\Users\\user\\Desktop\\aifinal\\static\\opt_spleeter", f"{base_name}_accompaniment.wav")

#         # 최종 오디오 합성
#         final_mix_path = await async_mix_audio(vocal_output_path, accompaniment_path, final_output_path)

#         if final_mix_path and isinstance(final_mix_path, str):
#             return FileResponse(final_output_path, filename=f"{base_name}_mix_audio.wav", media_type='audio/wav')
#         else:
#             logging.error("Failed to mix audio files: %s", final_mix_path.get("message", ""))
#             return {"error": "Failed to mix audio files.", "details": final_mix_path.get("message", "")}
#     else:
#         logging.error("Failed to convert audio file: %s", converted_file_result.get("message", ""))
#         return {"error": "Failed to convert audio file.", "details": converted_file_result.get("message", "")}


# # TTS
# # TTS
# # TTS
# # TTS
# # TTS
    
# # 결과 파일을 저장할 기본 디렉토리
# output_dir = "C:\\Users\\user\\Desktop\\aifinal\\static\\opt_tts"
# os.makedirs(output_dir, exist_ok=True)

# pth_dir = r"C:/Users/user/Desktop/aifinal/weights/pth"
# index_dir = r"C:/Users/user/Desktop/aifinal/weights/index"


# @app.post("/tts/")
# async def run_tts(
#     text: str = Form(...),
#     voice: str = Form(...),
#     pth_file_path: str = Form(...),  # 파일 경로를 문자열로 받음
#     index_file_path: str = Form(None),  # 파일 경로를 문자열로 받음, 선택적
#     index_rate: float = Form(...),
#     f0up_key: int = Form(...),
#     filter_radius: int = Form(...),
#     rms_mix_rate: float = Form(...),
#     protect: float = Form(...),
#     hop_length: int = Form(...),
#     f0method: str = Form(...),
#     split_audio: bool = Form(False),
#     f0autotune: bool = Form(False),
#     clean_audio: bool = Form(False),
#     clean_strength: float = Form(...),
#     export_format: str = Form(...)
# ):
#     # 파일 저장 경로 설정
#     output_tts_path = os.path.join(output_dir, "opt_tts.wav")
#     output_rvc_path = os.path.join(output_dir, "opt_rvc.wav")

#     # 파일 이름으로부터 전체 경로 구성
#     pth_file_path = os.path.join(pth_dir, pth_file_path)
#     index_file_path = os.path.join(index_dir, index_file_path) if index_file_path else ""

#     # TTS 및 음성 변환 스크립트 경로 설정
#     tts_script_path = os.path.join("rvc", "lib", "tools", "tts.py")
#     infer_script_path = os.path.join("rvc", "infer", "infer.py")

#     command_tts = [
#         "python",
#         tts_script_path,
#         text,
#         voice,
#         output_tts_path,
#     ]

#     command_infer = [
#         "python",
#         infer_script_path,
#         str(f0up_key),
#         str(filter_radius),
#         str(index_rate),
#         str(hop_length),
#         f0method,
#         output_tts_path,
#         output_rvc_path,
#         pth_file_path,
#         index_file_path if index_file_path else "",
#         str(split_audio),
#         str(f0autotune),
#         str(rms_mix_rate),
#         str(protect),
#         str(clean_audio),
#         str(clean_strength),
#         export_format,
#     ]

#     # subprocess를 사용하여 외부 스크립트 실행
#     subprocess.run(command_tts, check=True)
#     subprocess.run(command_infer, check=True)

#     # 변환된 오디오 파일을 클라이언트에게 스트리밍
#     return FileResponse(output_rvc_path, media_type='audio/wav', filename="opt_rvc.wav")


# # train
# # train
# # train
# # train
# # train
# config = Config()
# current_script_directory = os.path.dirname(os.path.realpath(__file__))
# logs_path = os.path.join(current_script_directory, "logs")

# # Preprocess
# def run_preprocess_script(model_name, dataset_path, sampling_rate):
#     per = 3.0 if config.is_half else 3.7
#     preprocess_script_path = os.path.join("rvc", "train", "preprocess", "preprocess.py")
#     command = [
#         "python",
#         preprocess_script_path,
#         *map(
#             str,
#             [
#                 os.path.join(logs_path, model_name),
#                 dataset_path,
#                 sampling_rate,
#                 per,
#             ],
#         ),
#     ]

#     os.makedirs(os.path.join(logs_path, model_name), exist_ok=True)
#     try:
#         subprocess.run(command, check=True)
#         return f"Model {model_name} preprocessed successfully."
#     except subprocess.CalledProcessError as e:
#         return f"Error in preprocessing model {model_name}: {e}"

# # Extract
# def run_extract_script(model_name, rvc_version, f0method, hop_length, sampling_rate):
#     model_path = os.path.join(logs_path, model_name)
#     extract_f0_script_path = os.path.join(
#         "rvc", "train", "extract", "extract_f0_print.py"
#     )
#     extract_feature_script_path = os.path.join(
#         "rvc", "train", "extract", "extract_feature_print.py"
#     )

#     command_1 = [
#         "python",
#         extract_f0_script_path,
#         *map(
#             str,
#             [
#                 model_path,
#                 f0method,
#                 hop_length,
#             ],
#         ),
#     ]
#     command_2 = [
#         "python",
#         extract_feature_script_path,
#         *map(
#             str,
#             [
#                 config.device,
#                 "1",
#                 "0",
#                 "0",
#                 model_path,
#                 rvc_version,
#                 "True",
#             ],
#         ),
#     ]
#     try:
#         subprocess.run(command_1, check=True)
#         subprocess.run(command_2, check=True)
#         generate_config(rvc_version, sampling_rate, model_path)
#         generate_filelist(f0method, model_path, rvc_version, sampling_rate)
#         return f"Model {model_name} extracted successfully."
#     except subprocess.CalledProcessError as e:
#         return f"Error in extracting features for model {model_name}: {e}"

# # Train
# def run_train_script(
#     model_name,
#     rvc_version,
#     save_every_epoch,
#     save_only_latest,
#     save_every_weights,
#     total_epoch,
#     sampling_rate,
#     batch_size,
#     gpu,
#     pitch_guidance,
#     pretrained,
#     custom_pretrained,
#     g_pretrained_path=None,
#     d_pretrained_path=None,
# ):
#     f0 = 1 if str(pitch_guidance) == "True" else 0
#     latest = 1 if str(save_only_latest) == "True" else 0
#     save_every = 1 if str(save_every_weights) == "True" else 0

#     if str(pretrained) == "True":
#         if str(custom_pretrained) == "False":
#             pg, pd = pretrained_selector(f0)[rvc_version][sampling_rate]
#         else:
#             if g_pretrained_path is None or d_pretrained_path is None:
#                 raise ValueError(
#                     "Please provide the path to the pretrained G and D models."
#                 )
#             pg, pd = g_pretrained_path, d_pretrained_path
#     else:
#         pg, pd = "", ""

#     train_script_path = os.path.join("rvc", "train", "train.py")
#     command = [
#         "python",
#         train_script_path,
#         *map(
#             str,
#             [
#                 "-se",
#                 save_every_epoch,
#                 "-te",
#                 total_epoch,
#                 "-pg",
#                 pg,
#                 "-pd",
#                 pd,
#                 "-sr",
#                 sampling_rate,
#                 "-bs",
#                 batch_size,
#                 "-g",
#                 gpu,
#                 "-e",
#                 os.path.join(logs_path, model_name),
#                 "-v",
#                 rvc_version,
#                 "-l",
#                 latest,
#                 "-c",
#                 "0",
#                 "-sw",
#                 save_every,
#                 "-f0",
#                 f0,
#             ],
#         ),
#     ]

#     try:
#         subprocess.run(command, check=True)
#         return f"Model {model_name} trained successfully."
#     except subprocess.CalledProcessError as e:
#         return f"Error in training model {model_name}: {e}"

# # Index
# def run_index_script(model_name, rvc_version):
#     index_script_path = os.path.join("rvc", "train", "process", "extract_index.py")
#     command = [
#         "python",
#         index_script_path,
#         os.path.join(logs_path, model_name),
#         rvc_version,
#     ]

#     try:
#         subprocess.run(command, check=True)
#         return f"Index file for {model_name} generated successfully."
#     except subprocess.CalledProcessError as e:
#         return f"Error in generating index file for model {model_name}: {e}"
    
#     # 예시로 주어진 동기 함수 중 하나를 사용하기 위한 비동기 래퍼 함수
# async def run_preprocess_script_async(model_name, dataset_path, sampling_rate):
#     # ThreadPoolExecutor를 사용할 필요가 없습니다.
#     result = await run_in_threadpool(
#         run_preprocess_script,  # 동기 함수 이름
#         model_name, dataset_path, sampling_rate  # 필요한 인자들
#     )
#     return result

# # 다른 함수들에 대해서도 비슷한 방법으로 래핑할 수 있습니다.
# async def run_extract_script_async(model_name, rvc_version, f0method, hop_length, sampling_rate):
#     result = await run_in_threadpool(
#         run_extract_script,
#         model_name, rvc_version, f0method, hop_length, sampling_rate
#     )
#     return result

# async def run_train_script_async(
#     model_name, rvc_version, save_every_epoch, save_only_latest, save_every_weights,
#     total_epoch, sampling_rate, batch_size, gpu, pitch_guidance, pretrained, custom_pretrained,
#     g_pretrained_path=None, d_pretrained_path=None):
#     result = await run_in_threadpool(
#         run_train_script,
#         model_name, rvc_version, save_every_epoch, save_only_latest, save_every_weights,
#         total_epoch, sampling_rate, batch_size, gpu, pitch_guidance, pretrained, custom_pretrained,
#         g_pretrained_path, d_pretrained_path
#     )
#     return result

# async def run_index_script_async(model_name, rvc_version):
#     result = await run_in_threadpool(
#         run_index_script,
#         model_name, rvc_version
#     )
#     return result

# # 사용 컨텍스트: run_in_executor는 asyncio의 일반적인 사용 사례에서,
# # 명시적으로 실행자(executor)를 관리하면서 동기 함수를 비동기적으로 실행할 때 사용됩니다.
# # 반면, run_in_threadpool은 FastAPI 또는 Starlette에서 제공하는 편의 기능으로,
# # 내부적으로 run_in_executor를 사용하지만 사용자가 실행자를 직접 관리할 필요가 없습니다.
# # 용이성: run_in_threadpool은 FastAPI와 같은 비동기 웹 애플리케이션에서 동기 함수를 더 쉽게 비동기적으로 실행할 수 있도록 해줍니다.
# # 사용자가 직접 ThreadPoolExecutor를 생성하고 관리하는 복잡성을 줄여줍니다.
# # 목적과 환경에 맞는 선택: 일반적인 asyncio 사용 사례에는 run_in_executor가,
# # FastAPI나 Starlette과 같은 특정 웹 프레임워크 내에서 더 간편한 사용을 원할 때는 run_in_threadpool이 더 적합할 수 있습니다.

# async def save_and_convert_files(files: List[UploadFile], recording_dir="static/recordings"):
#     os.makedirs(recording_dir, exist_ok=True)
#     valid_extensions = ('.mp3', '.m4a', '.wav')
    
#     for file in files:
#         # 파일 확장자 확인
#         if not file.filename.lower().endswith(valid_extensions):
#             # 유효하지 않은 파일이므로 건너뜁니다.
#             continue
        
#         # 파일 경로 준비
#         original_path = os.path.join(recording_dir, file.filename)
        
#         # 파일 저장
#         async with aiofiles.open(original_path, 'wb') as out_file:
#             content = await file.read()  # 파일 내용 읽기
#             await out_file.write(content)  # 파일 저장
            
#         # 클라이언트에서 직접 녹음한 파일인지 확인
#         if file.filename.lower().endswith('.wav'):
#             # WAV 파일은 변환 없이 저장되므로 추가 검사가 필요하지 않습니다.
#             continue
        
#         # ffmpeg를 사용하여 MP3 또는 M4A 파일을 WAV로 변환
#         new_filename = file.filename.rsplit('.', 1)[0] + '.wav'
#         new_path = os.path.join(recording_dir, new_filename)
        
#         # ffmpeg 변환 과정에서 발생하는 오류를 처리하기 위해 try-except 블록 사용
#         try:
#             subprocess.run(['ffmpeg', '-i', original_path, new_path], check=True)
#         except subprocess.CalledProcessError as e:
#             # 변환 중에 오류가 발생한 경우 원본 파일 삭제 후 다음 파일로 이동
#             os.remove(original_path)
#             continue
            
#         # 원본 파일 삭제 (WAV로 변환된 파일만 남깁니다.)
#         os.remove(original_path)

#     return recording_dir




# # 지정된 패턴에 일치하는 파일을 찾아 대상 경로로 복사하는 함수
# def copy_files_to_target(source_dir, target_dir, pattern):
#     os.makedirs(target_dir, exist_ok=True)  # 대상 경로가 없으면 생성
#     for file_path in glob.glob(os.path.join(source_dir, pattern)):
#         shutil.copy(file_path, target_dir)


# @app.exception_handler(StarletteHTTPException)
# async def http_exception_handler(request, exc):
#     logger.error(f"HTTP error: {exc.detail}")
#     return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

# @app.exception_handler(RequestValidationError)
# async def validation_exception_handler(request, exc):
#     logger.error(f"Validation error: {exc}")
#     return PlainTextResponse(str(exc), status_code=400)

# # 훈련 데이터 처리 및 모델 훈련 엔드포인트
# @app.post("/train/")
# async def train_model(
#     files: list[UploadFile] = File(...),
#     model_name: str = Form(...),
#     total_epoch: str = Form(...),
#     sampling_rate: str = Form(...),
#     rvc_version: str = Form(...),
#     f0method: str = Form(...),
#     hop_length: str = Form(...),
#     batch_size: str = Form(...),
#     gpu: str = Form(...),
#     pitch_guidance: str = Form(...),
#     pretrained: str = Form(...),
#     custom_pretrained: str = Form(...),
# ):
    
#     try:
#         # 파일 저장 및 변환
#         dataset_path = await save_and_convert_files(files)
#         # dataset_path = "C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\static\\recordings"

#         # 전처리
#         preprocess_result = await run_preprocess_script_async(model_name, dataset_path, sampling_rate)

#         # 특성 추출
#         extract_result = await run_extract_script_async(model_name, rvc_version, f0method, hop_length, sampling_rate)

#         # 모델 훈련
#         train_result = await run_train_script_async(
#             model_name, rvc_version, "10", "False", "True", total_epoch, sampling_rate, batch_size, gpu, pitch_guidance, pretrained, custom_pretrained
#         )
#         pth_target_path = "C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\pth"
#         copy_files_to_target(logs_path, pth_target_path, f"{model_name}*.pth")

#         # 인덱스 생성
#         index_result = await run_index_script_async(model_name, rvc_version)
#         # .index 파일을 지정된 경로로 복사
#         index_target_path = "C:\\Users\\user\\Desktop\\AI-X3_project_final_AI\\weights\\index"
#         copy_files_to_target(logs_path, index_target_path, f"{model_name}*.index")

#         return {"message": "Model training and processing completed successfully."}
    
#     except Exception as e:
#         logger.error(f"Internal server error occurred: {e}")
#         raise HTTPException(status_code=500, detail="Internal server error occurred.")

