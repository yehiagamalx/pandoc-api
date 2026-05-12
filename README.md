# pandoc-api

HTTP API server that converts `.docx` files to HTML + base64-encoded images using [Pandoc](https://pandoc.org/). Runs as a Docker container; designed to sit behind Nginx Proxy Manager on a VPS.

Used by the **ARI Publication Importer** WordPress plugin.

---

## API

### `POST /convert`

**Auth** (optional): `X-API-Key: <your-key>` — required when `PANDOC_API_KEY` is set.

**Request**: `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | A `.docx` file |

**Response 200**

```json
{
  "html": "<p>converted HTML…</p>",
  "images": {
    "media/image1.png": "<base64 string>"
  }
}
```

**Error responses**

| Code | Body |
|------|------|
| 400  | `{"error": "Missing 'file' field…"}` |
| 400  | `{"error": "File must be a .docx"}` |
| 401  | `{"error": "Unauthorized"}` |
| 500  | `{"error": "Pandoc conversion failed: …"}` |

### `GET /health`

Returns `{"status": "ok"}` — for uptime checks.

---

## Running locally

```bash
# Install deps (Python 3.12+, Pandoc must be on PATH)
pip install -r requirements.txt

# Copy and fill env
cp .env.example .env

# Start
python app.py
```

Test:

```bash
curl -X POST http://localhost:5000/convert \
  -H "X-API-Key: secret" \
  -F "file=@document.docx"
```

---

## Docker

### Build and run

```bash
docker build -t pandoc-api .
docker run -p 5000:5000 -e PANDOC_API_KEY=secret pandoc-api
```

### docker-compose (production)

```bash
cp .env.example .env
# Edit .env — set PANDOC_API_KEY

docker compose up -d
```

The `docker-compose.yml` includes **Watchtower**, which polls GHCR every 5 minutes and auto-updates the `pandoc-api` container when a new image is published.

> **GHCR auth for Watchtower**: mount your Docker config with GHCR credentials at `/root/.docker/config.json` on the host, as mapped in `docker-compose.yml`.

---

## Deployment (Nginx Proxy Manager)

1. Pull the image or use `docker-compose.yml` on your VPS.
2. In NPM, create a **Proxy Host** pointing to `http://<container-ip>:5000`.
3. Enable SSL (Let's Encrypt) on the NPM entry.
4. Set `PANDOC_API_KEY` in `.env` and restart the stack.

---

## Release & CI

Pushing a tag `v*` (e.g. `v1.0.0`) triggers the GitHub Actions workflow which:

1. Builds the Docker image.
2. Pushes it to `ghcr.io/yehiagamalx/pandoc-api:<tag>` and `:latest`.

Watchtower then picks up `:latest` within 5 minutes on any running server.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PANDOC_API_KEY` | _(empty)_ | If set, `X-API-Key` header is required |
| `PORT` | `5000` | Port Gunicorn listens on |
