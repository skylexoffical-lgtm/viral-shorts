#!/usr/bin/env python3

import os
import json
import uuid
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# -------------------------
# PATH SETUP
# -------------------------
BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "outputs"
TEMP_FOLDER = BASE_DIR / "temp"

for f in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    f.mkdir(exist_ok=True)

# -------------------------
# FLASK INIT
# -------------------------
app = Flask(__name__)
CORS(app)

jobs = {}

# -------------------------
# FRONTEND
# -------------------------
@app.route('/')
def index():
    return send_file(BASE_DIR / "index.html")


# -------------------------
# HEALTH CHECK
# -------------------------
@app.route('/api/health')
def health():
    return jsonify({
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "yt-dlp": shutil.which("yt-dlp") is not None
    })


# -------------------------
# DOWNLOAD VIDEO
# -------------------------
@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "url missing"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "downloading", "progress": 0}

    def task():
        try:
            out_file = UPLOAD_FOLDER / f"{job_id}.mp4"
            rel_out = os.path.relpath(out_file, BASE_DIR)

            cmd = [
                "yt-dlp",
                "-f", "best",
                "-o", rel_out,
                url
            ]

            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            for line in p.stdout:
                jobs[job_id]["progress"] = min(jobs[job_id]["progress"] + 5, 90)

            p.wait()

            jobs[job_id] = {
                "status": "completed",
                "video_path": str(out_file),
                "duration": 60
            }

        except Exception as e:
            jobs[job_id] = {"status": "error", "message": str(e)}

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})


# -------------------------
# JOB STATUS
# -------------------------
@app.route('/api/job/<job_id>')
def job(job_id):
    return jsonify(jobs.get(job_id, {}))


# -------------------------
# PREVIEW FRAME
# -------------------------
@app.route('/api/preview', methods=['POST'])
def preview():
    data = request.json
    video = data["video_path"]

    img = TEMP_FOLDER / f"{uuid.uuid4().hex}.jpg"
    rel_video = os.path.relpath(video, BASE_DIR)
    rel_img = os.path.relpath(img, BASE_DIR)

    subprocess.run([
        "ffmpeg", "-y",
        "-ss", "1",
        "-i", rel_video,
        "-vframes", "1",
        rel_img
    ])

    return jsonify({
        "image": f"/temp/{img.name}"
    })


@app.route('/temp/<file>')
def temp(file):
    return send_from_directory(TEMP_FOLDER, file)


# -------------------------
# ANALYZE (FAKE AI)
# -------------------------
@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    video = data["video_path"]

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "analyzing", "progress": 0}

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
            "clips": clips
        }

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})


# -------------------------
# GENERATE SHORTS (FFMPEG CORE)
# -------------------------
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    video = data["video_path"]
    clips = data["clips"]

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "processing", "progress": 0}

    def task():
        outputs = []

        for i, c in enumerate(clips):
            out = OUTPUT_FOLDER / f"short_{job_id}_{i}.mp4"
            rel_in = os.path.relpath(video, BASE_DIR)
            rel_out = os.path.relpath(out, BASE_DIR)

            subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(c["timestamp"]),
                "-t", str(c["duration"]),
                "-i", rel_in,
                "-vf", "scale=1080:1920",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                rel_out
            ])

            outputs.append({
                "url": f"/download/{out.name}"
            })

            jobs[job_id]["progress"] = int((i+1)/len(clips)*100)

        jobs[job_id] = {
            "status": "completed",
            "outputs": outputs
        }

    threading.Thread(target=task).start()
    return jsonify({"job_id": job_id})


# -------------------------
# DOWNLOAD FILE
# -------------------------
@app.route('/download/<file>')
def download(file):
    return send_file(OUTPUT_FOLDER / file, as_attachment=True)


# -------------------------
# START SERVER (RAILWAY FIX)
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
