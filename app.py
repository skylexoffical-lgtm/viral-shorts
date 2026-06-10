import os
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


def get_ydl_options(output_path):
    return {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    job_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_FOLDER, job_id)
    os.makedirs(output_path, exist_ok=True)

    try:
        with yt_dlp.YoutubeDL(get_ydl_options(output_path)) as ydl:
            info = ydl.extract_info(url, download=True)

        filename = ydl.prepare_filename(info)

        return jsonify({
            "status": "success",
            "title": info.get("title"),
            "file": filename,
            "job_id": job_id
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/download/<job_id>/<filename>")
def download_file(job_id, filename):
    folder = os.path.join(DOWNLOAD_FOLDER, job_id)
    return send_from_directory(folder, filename, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
