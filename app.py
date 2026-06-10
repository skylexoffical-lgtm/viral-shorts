import os
import uuid
import time
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

JOBS = {}

# ----------------------------
# FRONTEND
# ----------------------------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# ----------------------------
# HEALTH CHECK
# ----------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "ffmpeg_installed": True,
        "ytdlp_installed": True
    })

# ----------------------------
# DOWNLOAD (SIMULATION)
# ----------------------------
@app.route("/api/download", methods=["POST"])
def download():
    data = request.json
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "İndiriliyor...",
        "video_path": "video.mp4",
        "duration": 300,
        "width": 1920,
        "height": 1080
    }

    return jsonify({"job_id": job_id})

# ----------------------------
# ANALYZE (SIMULATION)
# ----------------------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Viral anlar aranıyor...",
        "clips": []
    }

    return jsonify({"job_id": job_id})

# ----------------------------
# GENERATE (SIMULATION)
# ----------------------------
@app.route("/api/generate", methods=["POST"])
def generate():
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Shorts üretiliyor...",
        "outputs": []
    }

    return jsonify({"job_id": job_id})

# ----------------------------
# JOB POLLING (CRITICAL)
# ----------------------------
@app.route("/api/job/<job_id>")
def job(job_id):
    job = JOBS.get(job_id)

    if not job:
        return jsonify({"status": "error", "message": "Job not found"})

    # fake progress simulation
    if job["progress"] < 100:
        job["progress"] += 20
        job["message"] = "İşleniyor..."
        if job["progress"] >= 100:
            job["status"] = "completed"

            if "clips" in job:
                job["clips"] = [
                    {"timestamp": 30, "duration": 8, "viral_score": 92, "type": "funny"},
                    {"timestamp": 120, "duration": 6, "viral_score": 88, "type": "reaction"}
                ]

            if "outputs" in job:
                job["outputs"] = [
                    {"url": "/video.mp4", "duration": 9, "size": "1080x1920"}
                ]

    return jsonify(job)

# ----------------------------
# PREVIEW (DUMMY IMAGE)
# ----------------------------
@app.route("/api/preview", methods=["POST"])
def preview():
    return jsonify({
        "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lp6j9QAAAABJRU5ErkJggg=="
    })

# ----------------------------
# START SERVER (IMPORTANT FOR RAILWAY)
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
