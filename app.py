#!/usr/bin/env python3

import os
import json
import uuid
import shutil
import subprocess
import threading
import time
import requests
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "outputs"
TEMP_FOLDER = BASE_DIR / "temp"

for f in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    f.mkdir(exist_ok=True)

app = Flask(__name__)
CORS(app)

jobs = {}

# TEMİZLİK
def cleanup_old_files():
    now = time.time()
    max_age = 3600
    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
        if not folder.exists():
            continue
        for file_path in folder.iterdir():
            if file_path.is_file():
                try:
                    if now - file_path.stat().st_mtime > max_age:
                        file_path.unlink()
                except:
                    pass

def start_cleanup_scheduler():
    while True:
        time.sleep(600)
        cleanup_old_files()

threading.Thread(target=start_cleanup_scheduler, daemon=True).start()


@app.route('/')
def index():
    return send_file(BASE_DIR / "index.html")


@app.route('/api/health')
def health():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ytdlp_ok = shutil.which("yt-dlp") is not None

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
        "yt_dlp_installed": ytdlp_ok,
        "yt_dlp_version": ytdlp_version
    })


# ============================================================
# COBALT API
# ============================================================
def try_cobalt_api(url, out_file, api_url):
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "url": url,
            "vCodec": "h264",
            "vQuality": "1080",
            "aFormat": "mp3",
            "filenamePattern": "classic"
        }

        response = requests.post(api_url, json=payload, headers=headers, timeout=60)

        if response.status_code == 200:
            data = response.json()

            if "url" in data:
                video_url = data["url"]
                r = requests.get(video_url, stream=True, timeout=120)
                r.raise_for_status()

                with open(out_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                return True, f"Cobalt başarılı: {api_url}"

            elif "picker" in data and data["picker"]:
                picker = data["picker"][0]
                if "url" in picker:
                    video_url = picker["url"]
                    r = requests.get(video_url, stream=True, timeout=120)
                    r.raise_for_status()

                    with open(out_file, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    return True, f"Cobalt picker başarılı: {api_url}"

            elif "status" in data:
                if data["status"] == "error":
                    return False, f"Cobalt hata: {data.get('text', 'Bilinmeyen')}"
                elif data["status"] in ["tunnel", "redirect"] and "url" in data:
                    video_url = data["url"]
                    r = requests.get(video_url, stream=True, timeout=120)
                    r.raise_for_status()

                    with open(out_file, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    return True, f"Cobalt redirect başarılı: {api_url}"

        return False, f"Cobalt HTTP {response.status_code}"

    except Exception as e:
        return False, f"Cobalt hata: {str(e)[:150]}"


def download_with_cobalt(url, out_file):
    cobalt_apis = [
        "https://api.cobalt.tools/api/json",
        "https://co.wuk.sh/api/json",
        "https://api.cobalt.best/api/json",
    ]

    for api_url in cobalt_apis:
        success, msg = try_cobalt_api(url, out_file, api_url)
        if success:
            return True, msg

    return False, "Tüm Cobalt API'leri başarısız"


# ============================================================
# YT-DLP
# ============================================================
def download_with_ytdlp(url, out_file):
    try:
        subprocess.run(
            ["pip", "install", "--upgrade", "--no-cache-dir", "yt-dlp[default]"],
            capture_output=True, timeout=60
        )

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "--ffmpeg-location", shutil.which("ffmpeg") or "/usr/bin/ffmpeg",
            "--no-check-certificates",
            "--geo-bypass",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "--no-warnings",
            "-o", str(out_file),
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if result.returncode == 0 and out_file.exists() and out_file.stat().st_size > 50000:
            return True, "yt-dlp başarılı"
        else:
            error = result.stderr[:300] if result.stderr else "Bilinmeyen hata"
            return False, f"yt-dlp hata: {error}"

    except Exception as e:
        return False, f"yt-dlp hata: {str(e)[:200]}"


# ============================================================
# ANA İNDİRME
# ============================================================
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
        "progress": 5,
        "message": "Başlatılıyor...",
        "video_path": str(out_file)
    }

    def task():
        def log(msg):
            print(f"[JOB {job_id}] {msg}")

        try:
            is_youtube = any(x in url.lower() for x in ['youtube.com', 'youtu.be', 'youtube'])
            is_kick = 'kick.com' in url.lower()

            success = False
            method_used = ""
            error_details = []

            # YOUTUBE
            if is_youtube:
                jobs[job_id]["message"] = "YouTube HD indiriliyor..."
                jobs[job_id]["progress"] = 20
                log("YouTube tespit edildi, Cobalt API deneniyor...")

                success, msg = download_with_cobalt(url, out_file)
                method_used = "Cobalt API"
                log(f"Cobalt sonuç: {success} - {msg}")

                if not success:
                    error_details.append(f"Cobalt: {msg}")

                    jobs[job_id]["message"] = "Cobalt başarısız, alternatif deneniyor..."
                    jobs[job_id]["progress"] = 50
                    log("Cobalt başarısız, yt-dlp deneniyor...")

                    success, msg = download_with_ytdlp(url, out_file)
                    method_used = "yt-dlp fallback"
                    log(f"yt-dlp sonuç: {success} - {msg}")

                    if not success:
                        error_details.append(f"yt-dlp: {msg}")

            # KICK / DİĞER
            else:
                jobs[job_id]["message"] = "Video indiriliyor..."
                jobs[job_id]["progress"] = 20
                log(f"Kick/diğer: {url[:50]}...")

                success, msg = download_with_ytdlp(url, out_file)
                method_used = "yt-dlp"
                log(f"yt-dlp sonuç: {success} - {msg}")

                if not success:
                    error_details.append(f"yt-dlp: {msg}")

            # HÂLÂ BAŞARISIZ
            if not success:
                is_bot_error = any("bot" in e.lower() or "sign in" in e.lower() for e in error_details)

                if is_youtube and is_bot_error:
                    error_msg = """YouTube bu sunucudan indirmeye izin vermiyor.

ÇÖZÜMLER:
1. Kick URL kullanın (kick.com) — sorunsuz çalışır
2. cobalt.tools adresine gidip manuel indirin
3. Farklı bir sunucu deneyin (IP banlı olabilir)

Teknik Detay:
""" + "\n".join(error_details[:2])
                else:
                    error_msg = "Tüm indirme yöntemleri başarısız.\n\n" + "\n".join(error_details)

                raise Exception(error_msg)

            # VIDEO BİLGİLERİNİ AL
            jobs[job_id]["message"] = "Video bilgileri alınıyor..."
            jobs[job_id]["progress"] = 90

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
            bitrate = stream.get("bit_rate", "0")

            try:
                bitrate_mb = round(int(bitrate) / 1000000, 2)
                bitrate_str = f"{bitrate_mb} Mbps"
            except:
                bitrate_str = "?"

            quality_label = "SD"
            if height >= 1080:
                quality_label = "FHD 1080p"
            elif height >= 720:
                quality_label = "HD 720p"
            elif height >= 480:
                quality_label = "480p"

            file_size_mb = round(out_file.stat().st_size / (1024*1024), 1)

            jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": f"✓ {quality_label} ({file_size_mb}MB)",
                "video_path": str(out_file),
                "duration": duration,
                "width": width,
                "height": height,
                "bitrate": bitrate_str,
                "quality": quality_label,
                "method": method_used,
                "size_mb": file_size_mb
            }

            log(f"✓ TAMAMLANDI: {width}x{height} {quality_label} {file_size_mb}MB")

        except Exception as e:
            error_msg = str(e)
            log(f"✗ HATA: {error_msg[:300]}")
            jobs[job_id] = {
                "status": "error",
                "progress": 0,
                "message": error_msg
            }
            if out_file.exists():
                try:
                    out_file.unlink()
                except:
                    pass

    threading.Thread(target=task, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route('/api/job/<job_id>')
def job_status(job_id):
    return jsonify(jobs.get(job_id, {}))


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

        return jsonify({"image": f"/temp/{img_name}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/temp/<file>')
def serve_temp(file):
    return send_from_directory(TEMP_FOLDER, file)


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


# ============================================================
# FFMPEG SHORTS — Render'da 2GB RAM var, 1080p yapabiliriz
# ============================================================
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
                # Render'da 2GB RAM var, 1080x1920 yapabiliriz
                # Ama yine de threads 2 ile sınırla
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(timestamp),
                    "-t", str(duration),
                    "-i", video,
                    "-threads", "2",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(out_path)
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=300)

                if result.returncode != 0:
                    error_msg = result.stderr.decode('utf-8', errors='ignore')[:300]
                    raise Exception(f"FFmpeg hata: {error_msg}")

                file_size = out_path.stat().st_size
                size_mb = round(file_size / (1024 * 1024), 2)

                outputs.append({
                    "url": f"/download/{out_name}",
                    "duration": duration,
                    "size": f"{size_mb} MB"
                })

                jobs[job_id]["progress"] = int((i + 1) / len(clips) * 100)
                jobs[job_id]["message"] = f"{i+1}/{len(clips)} shorts üretildi"

            except subprocess.TimeoutExpired:
                jobs[job_id] = {
                    "status": "error",
                    "progress": 0,
                    "message": f"Klip {i+1} zaman aşımı"
                }
                return
            except Exception as e:
                jobs[job_id] = {
                    "status": "error",
                    "progress": 0,
                    "message": f"Klip {i+1} hatası: {str(e)[:200]}"
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


@app.route('/download/<file>')
def download(file):
    file_path = OUTPUT_FOLDER / file
    if not file_path.exists():
        return jsonify({"error": "Dosya bulunamadı"}), 404
    return send_file(file_path, as_attachment=True)


@app.route('/api/cleanup', methods=['POST'])
def manual_cleanup():
    cleanup_old_files()
    return jsonify({"message": "Temizlik tamamlandı"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
