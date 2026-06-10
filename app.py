#!/usr/bin/env python3

import os
import uuid
import shutil
import subprocess
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "outputs"
TEMP_FOLDER = BASE_DIR / "temp"

for f in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    f.mkdir(exist_ok=True)

app = Flask(__name__)
CORS(app)

jobs = {}

# ---------------- HEALTH ----------------
@app.route("/api/health")
def health():
    return jsonify({
        "ffmpeg_installed": shutil.which("ffmpeg") is not None,
        "ytdlp_installed": shutil.which("yt-dlp") is not None
    })

# ---------------- DOWNLOAD ----------------
@app.route("/api/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "message": "Başlıyor..."
    }

    def task():
        try:
            out_file = UPLOAD_FOLDER / f"{job_id}.mp4"
            cmd = [
                "yt-dlp",
                "-f", "best",
                "-o", str(out_file),
                url
            ]

            jobs[job_id]["message"] = "İndiriliyor..."

            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            for _ in p.stdout:
                jobs[job_id]["progress"] = min(jobs[job_id]["progress"] + 5, 90)

            p.wait()

            jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": "Bitti",
                "video_path": str(out_file),
                "duration": 60
            }

        except Exception as e:
            jobs[job_id] = {
                "status": "error",
                "message": str(e),
                "progress": 0
            }

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})

# ---------------- JOB ----------------
@app.route("/api/job/<job_id>")
def job(job_id):
    return jsonify(jobs.get(job_id, {}))

# ---------------- PREVIEW ----------------
@app.route("/api/preview", methods=["POST"])
def preview():
    data = request.json
    video = str(Path(data["video_path"]).resolve())

    img = TEMP_FOLDER / f"{uuid.uuid4().hex}.jpg"

    subprocess.run([
        "ffmpeg", "-y",
        "-ss", "1",
        "-i", video,
        "-vframes", "1",
        str(img)
    ])

    return jsonify({"image": f"/temp/{img.name}"})

@app.route("/temp/<file>")
def temp(file):
    return send_from_directory(TEMP_FOLDER, file)

# ---------------- ANALYZE ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "status": "analyzing",
        "progress": 0,
        "message": "Analiz başlıyor..."
    }

    def task():
        clips = []
        for i in range(6):
            clips.append({
                "timestamp": i * 10,
                "duration": 8,
                "viral_score": 70 + i * 5,
                "type": "viral"
            })

        jobs[job_id] = {
            "status": "completed",
            "progress": 100,
            "clips": clips,
            "message": "Tamamlandı"
        }

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})

# ---------------- GENERATE ----------------
@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.json
    video = str(Path(data["video_path"]).resolve())
    clips = data["clips"]

    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Başlıyor..."
    }

    def task():
        outputs = []

        for i, c in enumerate(clips):
            out = OUTPUT_FOLDER / f"short_{job_id}_{i}.mp4"

            subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(c["timestamp"]),
                "-t", str(c["duration"]),
                "-i", video,
                "-vf", "scale=1080:1920",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                str(out)
            ])

            outputs.append({
                "url": f"/download/{out.name}",
                "duration": c["duration"]
            })

            jobs[job_id]["progress"] = int((i + 1) / len(clips) * 100)

        jobs[job_id] = {
            "status": "completed",
            "outputs": outputs,
            "progress": 100
        }

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})

# ---------------- DOWNLOAD FILE ----------------
@app.route("/download/<file>")
def download_file(file):
    return send_file(OUTPUT_FOLDER / file, as_attachment=True)

# ---------------- START ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
