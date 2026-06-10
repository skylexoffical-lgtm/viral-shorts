import os
import uuid
import threading
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

JOBS = {}

# ---------------- FRONTEND ----------------
@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# ---------------- HEALTH ----------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "ffmpeg": True,
        "yt_dlp": True
    })


# ---------------- DOWNLOAD ----------------
def download_video(job_id, url):
    try:
        out = f"downloads/{job_id}.mp4"
        os.makedirs("downloads", exist_ok=True)

        cmd = [
            "yt-dlp",
            "-f", "best",
            "-o", out,
            url
        ]

        JOBS[job_id]["message"] = "Video indiriliyor..."
        subprocess.run(cmd, check=True)

        JOBS[job_id]["video_path"] = out
        JOBS[job_id]["progress"] = 50

        analyze_video(job_id)

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = str(e)


# ---------------- ANALYZE + CLIP ----------------
def analyze_video(job_id):
    try:
        video = JOBS[job_id]["video_path"]
        os.makedirs("outputs", exist_ok=True)

        # basit 2 clip üret
        clips = [
            {"timestamp": 10, "duration": 8, "viral_score": 92, "type": "funny"},
            {"timestamp": 40, "duration": 6, "viral_score": 88, "type": "reaction"}
        ]

        JOBS[job_id]["clips"] = clips
        JOBS[job_id]["progress"] = 80
        JOBS[job_id]["message"] = "Klipler hazırlandı"

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = str(e)


# ---------------- GENERATE SHORTS ----------------
def generate(job_id, clips):
    try:
        video = JOBS[job_id]["video_path"]
        outputs = []

        os.makedirs("outputs", exist_ok=True)

        for i, c in enumerate(clips):
            out_file = f"outputs/{job_id}_{i}.mp4"

            cmd = [
                "ffmpeg",
                "-y",
                "-i", video,
                "-ss", str(c["timestamp"]),
                "-t", str(c["duration"]),
                "-vf", "scale=1080:1920",
                out_file
            ]

            subprocess.run(cmd, check=True)

            outputs.append({
                "url": "/" + out_file,
                "duration": c["duration"],
                "size": "1080x1920"
            })

        JOBS[job_id]["outputs"] = outputs
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["message"] = "Bitti"

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = str(e)


# ---------------- API DOWNLOAD ----------------
@app.route("/api/download", methods=["POST"])
def download():
    url = request.json["url"]
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Başladı",
        "video_path": None
    }

    threading.Thread(target=download_video, args=(job_id, url)).start()

    return jsonify({"job_id": job_id})


# ---------------- ANALYZE ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Analiz",
        "clips": []
    }

    return jsonify({"job_id": job_id})


# ---------------- GENERATE ----------------
@app.route("/api/generate", methods=["POST"])
def generate_api():
    data = request.json
    job_id = str(uuid.uuid4())

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Üretiliyor"
    }

    threading.Thread(target=generate, args=(job_id, data["clips"])).start()

    return jsonify({"job_id": job_id})


# ---------------- JOB ----------------
@app.route("/api/job/<job_id>")
def job(job_id):
    return jsonify(JOBS.get(job_id, {"status": "not_found"}))


# ---------------- PREVIEW ----------------
@app.route("/api/preview", methods=["POST"])
def preview():
    return jsonify({
        "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lp6j9QAAAABJRU5ErkJggg=="
    })


# ---------------- START ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
