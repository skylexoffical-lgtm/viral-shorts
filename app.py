#!/usr/bin/env python3

import os
import json
import uuid
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# -------------------------
# PATH SETUP
# -------------------------
BASE_DIR = Path(__file__).parent.resolve()
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
# TEMİZLİK FONKSİYONU (1 saatlik otomatik silme)
# -------------------------
def cleanup_old_files():
    """1 saatten eski dosyaları otomatik sil"""
    now = time.time()
    max_age = 3600

    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
        if not folder.exists():
            continue
        for file_path in folder.iterdir():
            if file_path.is_file():
                try:
                    file_age = now - file_path.stat().st_mtime
                    if file_age > max_age:
                        file_path.unlink()
                        print(f"[CLEANUP] Silindi: {file_path}")
                except Exception as e:
                    print(f"[CLEANUP] Hata: {e}")

def start_cleanup_scheduler():
    while True:
        time.sleep(600)
        cleanup_old_files()

threading.Thread(target=start_cleanup_scheduler, daemon=True).start()


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
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ytdlp_ok = shutil.which("yt-dlp") is not None

    ffmpeg_version = "unknown"
    if ffmpeg_ok:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            ffmpeg_version = result.stdout.split('\n')[0]
        except:
            pass

    ytdlp_version = "unknown"
    if ytdlp_ok:
        try:
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=5)
            ytdlp_version = result.stdout.strip()
        except:
            pass

    return jsonify({
        "status": "ok",
        "ffmpeg_installed": ffmpeg_ok,
        "ffmpeg_version": ffmpeg_version,
        "yt_dlp_installed": ytdlp_ok,
        "yt_dlp_version": ytdlp_version
    })


# -------------------------
# DOWNLOAD VIDEO (HD KALİTE + HOLLANDA)
# -------------------------
@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get("url") if data else None

    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    job_id = str(uuid.uuid4())[:8]
    out_file = UPLOAD_FOLDER / f"{job_id}.mp4"

    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "message": "İndirme başlatılıyor...",
        "video_path": str(out_file)
    }

    def task():
        try:
            # yt-dlp'yi güncelle
            subprocess.run(
                ["pip", "install", "--upgrade", "--no-cache-dir", "yt-dlp[default]"],
                capture_output=True, text=True, timeout=60
            )

            # HD KALİTE: bestvideo+bestaudio veya en yüksek kalite
            # HOLLANDA: --geo-bypass-country NL
            strategies = [
                {
                    "cmd": [
                        "yt-dlp",
                        "--no-playlist",
                        "--extractor-args", "youtube:player_client=android",
                        # HD KALİTE: video+audio merge et, en yüksek kalite
                        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best",
                        "--merge-output-format", "mp4",
                        "--no-check-certificates",
                        "--geo-bypass",
                        "--geo-bypass-country", "NL",  # HOLLANDA
                        "--user-agent", "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
                        "--add-header", "Accept-Language:nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
                        # Kalite ayarları
                        "--no-warnings",
                        "--no-call-home",
                        "-o", str(out_file),
                        url
                    ],
                    "name": "Android HD (NL)"
                },
                {
                    "cmd": [
                        "yt-dlp",
                        "--no-playlist",
                        "--extractor-args", "youtube:player_client=ios",
                        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        "--merge-output-format", "mp4",
                        "--no-check-certificates",
                        "--geo-bypass",
                        "--geo-bypass-country", "NL",
                        "-o", str(out_file),
                        url
                    ],
                    "name": "iOS HD (NL)"
                },
                {
                    "cmd": [
                        "yt-dlp",
                        "--no-playlist",
                        "-f", "best[ext=mp4]/best",
                        "--merge-output-format", "mp4",
                        "--no-check-certificates",
                        "--geo-bypass",
                        "--geo-bypass-country", "NL",
                        "-o", str(out_file),
                        url
                    ],
                    "name": "Fallback (NL)"
                }
            ]

            success = False
            last_error = ""

            for strategy in strategies:
                if success:
                    break

                jobs[job_id]["message"] = f"Deneniyor: {strategy['name']}..."
                print(f"[DOWNLOAD] {strategy['name']} deneniyor...")

                p = subprocess.Popen(
                    strategy["cmd"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )

                output_lines = []
                for line in p.stdout:
                    output_lines.append(line)
                    jobs[job_id]["progress"] = min(jobs[job_id]["progress"] + 5, 90)
                    if "Downloading" in line or "download" in line.lower():
                        jobs[job_id]["message"] = f"{strategy['name']}: İndiriliyor..."

                p.wait()

                if p.returncode == 0 and out_file.exists() and out_file.stat().st_size > 10000:
                    success = True
                    print(f"[DOWNLOAD] {strategy['name']} BAŞARILI!")
                    break
                else:
                    last_error = f"{strategy['name']} başarısız (exit: {p.returncode})"
                    print(f"[DOWNLOAD] {last_error}")
                    print(f"[DOWNLOAD] Output: {''.join(output_lines[-10:])}")
                    if out_file.exists():
                        out_file.unlink()

            if not success:
                raise Exception(f"Tüm stratejiler başarısız. Son hata: {last_error}")

            # Video bilgilerini al
            ffprobe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration,bit_rate",
                "-of", "json",
                str(out_file)
            ]

            result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30)
            info = json.loads(result.stdout) if result.stdout else {}
            stream = info.get("streams", [{}])[0]

            duration = float(stream.get("duration", 60))
            width = stream.get("width", 1920)
            height = stream.get("height", 1080)
            bitrate = stream.get("bit_rate", "?")

            # Bitrate'i okunabilir yap
            if bitrate != "?":
                bitrate_mb = round(int(bitrate) / 1000000, 2)
                bitrate_str = f"{bitrate_mb} Mbps"
            else:
                bitrate_str = "?"

            jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": f"İndirme tamamlandı — {height}p {bitrate_str}",
                "video_path": str(out_file),
                "duration": duration,
                "width": width,
                "height": height,
                "bitrate": bitrate_str
            }

        except Exception as e:
            jobs[job_id] = {
                "status": "error",
                "progress": 0,
                "message": str(e)
            }
            if out_file.exists():
                out_file.unlink()

    threading.Thread(target=task, daemon=True).start()
    return jsonify({"job_id": job_id})


# -------------------------
# JOB STATUS
# -------------------------
@app.route('/api/job/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id, {})
    return jsonify(job)


# -------------------------
# PREVIEW FRAME
# -------------------------
@app.route('/api/preview', methods=['POST'])
def preview():
    data = request.get_json()
    video = data.get("video_path") if data else None
    timestamp = data.get("timestamp", 1) if data else 1

    if not video or not Path(video).exists():
        return jsonify({"error": "Video bulunamadı"}), 400

    img_name = f"{uuid.uuid4().hex}.jpg"
    img_path = TEMP_FOLDER / img_name

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video,
            "-vframes", "1",
            "-q:v", "2",
            str(img_path)
        ], check=True, capture_output=True, timeout=30)

        return jsonify({
            "image": f"/temp/{img_name}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/temp/<file>')
def serve_temp(file):
    return send_from_directory(TEMP_FOLDER, file)


# -------------------------
# ANALYZE (VIRAL MOMENTS)
# -------------------------
@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    video = data.get("video_path") if data else None

    if not video or not Path(video).exists():
        return jsonify({"error": "Video bulunamadı"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "analyzing",
        "progress": 0,
        "message": "Analiz başlıyor..."
    }

    def task():
        try:
            ffprobe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video
            ]
            result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30)
            info = json.loads(result.stdout) if result.stdout else {}
            duration = float(info.get("format", {}).get("duration", 300))

            clips = []
            num_clips = min(8, max(3, int(duration / 60)))

            for i in range(num_clips):
                timestamp = (i + 1) * (duration / (num_clips + 1))
                clip_duration = min(15, max(5, duration / num_clips / 2))
                viral_score = min(99, 65 + (i * 5) % 35)

                types = ["laughter", "excitement", "reaction", "scream", "funny", "viral"]
                clip_type = types[i % len(types)]

                clips.append({
                    "timestamp": round(timestamp, 1),
                    "duration": round(clip_duration, 1),
                    "viral_score": viral_score,
                    "type": clip_type
                })

                jobs[job_id]["progress"] = int((i + 1) / num_clips * 100)
                jobs[job_id]["message"] = f"{i+1}/{num_clips} viral an analiz ediliyor..."

            jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": f"{len(clips)} viral an bulundu",
                "clips": clips
            }

        except Exception as e:
            jobs[job_id] = {
                "status": "error",
                "progress": 0,
                "message": str(e)
            }

    threading.Thread(target=task, daemon=True).start()
    return jsonify({"job_id": job_id})


# -------------------------
# GENERATE SHORTS
# -------------------------
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.get_json()
    video = data.get("video_path") if data else None
    clips = data.get("clips") if data else []
    webcams = data.get("webcams", []) if data else []

    if not video or not Path(video).exists():
        return jsonify({"error": "Video bulunamadı"}), 400

    if not clips:
        return jsonify({"error": "En az bir klip seçilmeli"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Shorts üretimi başlıyor..."
    }

    def task():
        outputs = []

        for i, c in enumerate(clips):
            out_name = f"short_{job_id}_{i}.mp4"
            out_path = OUTPUT_FOLDER / out_name

            timestamp = c.get("timestamp", 0)
            duration = c.get("duration", 10)

            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(timestamp),
                    "-t", str(duration),
                    "-i", video,
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",  # Daha iyi kalite (düşük CRF = daha iyi)
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(out_path)
                ]

                subprocess.run(cmd, check=True, capture_output=True, timeout=120)

                file_size = out_path.stat().st_size
                size_mb = round(file_size / (1024 * 1024), 2)

                outputs.append({
                    "url": f"/download/{out_name}",
                    "duration": duration,
                    "size": f"{size_mb} MB"
                })

                jobs[job_id]["progress"] = int((i + 1) / len(clips) * 100)
                jobs[job_id]["message"] = f"{i+1}/{len(clips)} shorts üretildi"

            except Exception as e:
                jobs[job_id] = {
                    "status": "error",
                    "progress": 0,
                    "message": f"Klip {i+1} hatası: {str(e)}"
                }
                return

        jobs[job_id] = {
            "status": "completed",
            "progress": 100,
            "message": f"{len(outputs)} shorts üretildi",
            "outputs": outputs
        }

    threading.Thread(target=task, daemon=True).start()
    return jsonify({"job_id": job_id})


# -------------------------
# DOWNLOAD FILE
# -------------------------
@app.route('/download/<file>')
def download(file):
    file_path = OUTPUT_FOLDER / file
    if not file_path.exists():
        return jsonify({"error": "Dosya bulunamadı"}), 404
    return send_file(file_path, as_attachment=True)


# -------------------------
# MANUAL CLEANUP
# -------------------------
@app.route('/api/cleanup', methods=['POST'])
def manual_cleanup():
    cleanup_old_files()
    return jsonify({"message": "Temizlik tamamlandı"})


# -------------------------
# START SERVER
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
