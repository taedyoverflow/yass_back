# YASS AI

**Live URL**: [https://yass-ai.com](https://yass-ai.com)

YouTube Audio Separation, TTS, MIDI Conversion AI

유튜브 음원 분리, TTS(Text-to-Speech) 음성 합성, WAV 오디오의 MIDI 변환까지 다양한 기능을 지원하는 실시간 AI 웹 서비스입니다. 분리된 음원, 생성된 음성, 변환된 MIDI/악보 파일은 모두 스트리밍 및 다운로드가 가능합니다.

---

## Features

- **YouTube Search**: 유튜브 영상 검색 및 썸네일 리스트 제공
- **Audio Separation**
  - Spleeter 기반 (보컬/반주 2트랙 분리)
  - Demucs 기반 (보컬/드럼/베이스/기타 4트랙 분리)
- **Streaming & Download**: MinIO Public Bucket URL을 통해 직접 스트리밍/다운로드
- **Text-to-Speech**: Edge-TTS 기반 자연스러운 음성 생성
- **Audio to MIDI Conversion**: Basic Pitch 기반 오디오(MR) -> MIDI 변환 및 악보(PDF) 제공
- **Async Processing**: Celery + Redis 기반 비동기 작업 처리
- **Object Storage**: MinIO에 파일 저장 (일정 시간 후 자동 삭제)
- **Frontend**: React (Material UI 기반)
- **Backend**: FastAPI (Docker 외부에서 실행)

---

## Architecture (YouTube Audio Separation / TTS)

```mermaid
flowchart TD
    A[React Frontend] -->|JSON Request| B(FastAPI Backend)
    B -->|Send Task| C[Celery Worker]
    C -->|Download/Separate/TTS| D[MinIO Public Bucket]
    D -->|Public URL| B
    B -->|Response| A
    A -->|Polling (5 sec)| B
```

> 🎯 Separation과 TTS 결과는 **MinIO Public Bucket**에 저장되어 Presigned URL 없이도 접근 가능합니다.


---

## Architecture (Audio to MIDI Conversion)

```mermaid
flowchart TD
    A[React Frontend] -->|File Upload (wav)| B(FastAPI Backend)
    B -->|Send Task| C[Celery Worker]
    C -->|Basic Pitch + MuseScore| D[MinIO Public Bucket]
    D -->|MIDI URL + PDF URL| B
    B -->|Response| A
```

> 🎼 오디오 파일 업로드 후, Basic Pitch 모델로 MIDI 변환 → MuseScore로 PDF 악보 변환 → MinIO 저장 구조입니다.


---

## Tech Stack

### Frontend
- React + Material UI
- Pagination UX 개선 (페이지 이동 시 자동 스크롤 최상단)
- 오디오 스트리밍 및 다운로드를 위한 URL 기반 처리

### Backend
- FastAPI
- Celery + Redis (비동기 작업 큐)
- yt-dlp (YouTube 오디오 다운로드)
- Spleeter (오디오 소스 분리)
- Demucs (AI 기반 고급 오디오 소스 분리)
- Edge-TTS (텍스트 음성 변환)
- Basic Pitch (오디오 -> MIDI 변환)
- MuseScore (MIDI -> PDF 악보 변환)

### Infrastructure
- MinIO (Public Bucket 기반 스토리지)
- Docker (Frontend, Infrastructure 구성용)
- Nginx + Certbot (HTTPS Reverse Proxy)

> ⚡ FastAPI 서버는 현재 Docker 외부 `user1` 가상환경에서 구동 중입니다. (Chrome 세션 기반 yt-dlp 인증 유지 목적)


---

## 비동기 처리 흐름

### YouTube Separation / TTS 요청 시
1. URL 또는 텍스트를 입력하여 요청 전송
2. FastAPI가 Celery에 작업(Task)을 등록하고 task_id 반환
3. Celery가 yt-dlp 다운로드 → Spleeter/Demucs 분리 또는 TTS 합성 수행
4. 결과 파일을 MinIO Public Bucket에 저장
5. 프론트엔드는 주기적(5초 간격)으로 task_id로 상태 확인 (Polling)
6. 작업 완료 시 파일 URL을 받아 스트리밍 및 다운로드 제공


### Audio to MIDI 요청 시
1. WAV 파일을 업로드하여 요청 전송
2. FastAPI가 Celery에 작업 등록
3. Celery가 Basic Pitch로 MIDI 변환 및 MuseScore로 PDF 변환 수행
4. 결과 파일을 MinIO Public Bucket에 저장
5. 완료된 MIDI URL, BPM 정보, PDF 악보 URL을 프론트엔드로 반환


---

## 만든 이유

- 직접 필요해서 만들었어요  
- 아무도 개발 안 시켜줘서 스스로 만들어봤습니다  
- 실전에서 돌아가는 AI 웹서비스를 구현해보고 싶었어요


---

## Contact

📧 Email: [taedyoverflow@gmail.com](mailto:taedyoverflow@gmail.com)

🧠 Made by **Taedy**