"""
SubtitleAI Backend Server (ffmpeg edition — no moviepy needed)
Converts video/audio files to Khmer SRT subtitles using Faster-Whisper.
Run with: uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os
import uuid
import asyncio
import shutil
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs: dict = {}
whisper_model: WhisperModel = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global whisper_model
    print("Loading Whisper model (small)...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Whisper model ready.")
    yield

app = FastAPI(title="SubtitleAI API", lifespan=lifespan)

def format_timestamp(seconds: float) -> str:
    hours   = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs    = int(seconds % 60)
    millis  = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def extract_audio_ffmpeg(input_path: str, output_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr}")

def transcribe_to_srt(audio_path: str, language: str = "km"):
    segments, info = whisper_model.transcribe(
        audio_path,
        beam_size=5,
        language=language if language != "auto" else None,
        task="transcribe",
        initial_prompt="សួស្តី នេះគឺជាអត្ថបទជាភាសាខ្មែរ" if language == "km" else None,
    )
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = format_timestamp(seg.start)
        end   = format_timestamp(seg.end)
        lines.append(f"{i}\n{start} --> {end}\n{seg.text.strip()}\n")
    return "\n".join(lines), info.language

def cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

def run_transcription_job(job_id: str, input_path: str, language: str):
    audio_path = None
    try:
        jobs[job_id]["status"] = "extracting"
        ext = Path(input_path).suffix.lower()
        if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
            audio_path = str(UPLOAD_DIR / f"{job_id}_audio.wav")
            extract_audio_ffmpeg(input_path, audio_path)
        else:
            audio_path = input_path

        jobs[job_id]["status"] = "transcribing"
        srt_content, detected_lang = transcribe_to_srt(audio_path, language)

        srt_path = str(OUTPUT_DIR / f"{job_id}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        jobs[job_id].update({"status": "done", "file": srt_path, "language": detected_lang})
    except Exception as e:
        jobs[job_id].update({"status": "error", "error": str(e)})
    finally:
        cleanup(input_path)
        if audio_path and audio_path != input_path:
            cleanup(audio_path)

@app.get("/health")
def health():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        ffmpeg_ok = True
    except Exception:
        ffmpeg_ok = False
    return {"status": "ok", "model": "whisper-small", "ffmpeg": ffmpeg_ok}

@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...), language: str = "km"):
    allowed = {".mp4",".mkv",".mov",".avi",".webm",".mp3",".wav",".ogg",".m4a",".aac"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    job_id    = str(uuid.uuid4())
    save_path = str(UPLOAD_DIR / f"{job_id}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    jobs[job_id] = {"status": "queued", "file": None, "error": None}
    background_tasks.add_task(asyncio.get_event_loop().run_in_executor, None, run_transcription_job, job_id, save_path, language)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job_id, "status": job["status"], "language": job.get("language"), "error": job.get("error")}

@app.get("/download/{job_id}")
def download_srt(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready. Status: {job['status']}")
    srt_path = job["file"]
    if not srt_path or not os.path.exists(srt_path):
        raise HTTPException(500, "SRT file missing")
    return FileResponse(srt_path, media_type="text/plain", filename="subtitles.srt")
