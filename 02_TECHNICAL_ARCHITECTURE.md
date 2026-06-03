# Arquitetura Técnica

## Stack
### Backend
- Python 3.12+
- FastAPI

### IA
- YOLO11n
- ByteTrack

### Processamento de Vídeo
- OpenCV
- FFmpeg

### Banco
- SQLite

### Frontend
- Jinja2
- Bootstrap

## Pipeline
Vídeo -> Frames -> YOLO11n -> ByteTrack -> Agrupamento -> Snapshot -> Clipe -> SQLite -> Relatórios

## APIs
- GET /
- GET /events
- GET /events/{id}
- POST /process
- GET /status
