import base64
import hmac
import os
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

API_KEY = os.environ.get("PANDOC_API_KEY", "").strip()
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 50 * 1024 * 1024))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _check_auth():
    if not API_KEY:
        return None
    provided = request.headers.get("X-API-Key", "").strip()
    if not hmac.compare_digest(provided, API_KEY):
        return jsonify({"error": "Unauthorized"}), 401
    return None


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/convert", methods=["POST"])
def convert():
    auth_error = _check_auth()
    if auth_error:
        return auth_error

    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field in multipart form"}), 400

    upload = request.files["file"]
    if not upload.filename or not upload.filename.lower().endswith(".docx"):
        return jsonify({"error": "File must be a .docx"}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "input.docx"
        media_dir = Path(tmpdir) / "media"
        html_path = Path(tmpdir) / "output.html"

        upload.save(docx_path)

        result = subprocess.run(
            [
                "pandoc",
                str(docx_path),
                "-o", str(html_path),
                "--extract-media", str(tmpdir),
                "--html-q-tags",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return jsonify({"error": f"Pandoc conversion failed: {result.stderr.strip()}"}), 500

        html_content = html_path.read_text(encoding="utf-8")

        images = {}
        if media_dir.exists():
            for img_path in sorted(media_dir.rglob("*")):
                if img_path.is_file():
                    rel = img_path.relative_to(tmpdir)
                    images[str(rel)] = base64.b64encode(img_path.read_bytes()).decode("utf-8")

        return jsonify({"html": html_content, "images": images})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
