# Flask + Docker + GHCR Deployment Architecture

> In the context of building a Pandoc DOCX-to-HTML conversion API, facing the choice of web framework, container strategy, and deployment pipeline, I decided to use Flask + Gunicorn inside a Python slim Docker image, publish images to GHCR via GitHub Actions, and manage auto-updates with Watchtower, to achieve a self-contained, zero-downtime deployment on a VPS behind Nginx Proxy Manager, accepting the trade-off of requiring a GHCR auth credential on the server for Watchtower.

## Context

The pandoc-api is called by the ARI Publication Importer WordPress plugin on a VPS that already runs Docker and Nginx Proxy Manager. The server has no Python runtime — only Docker. The API does file I/O and shell-outs to Pandoc; it is not compute-intensive. The deployment model is: push a git tag → CI builds the image → Watchtower pulls it within 5 minutes.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Flask + Gunicorn** | Minimal, well-understood, no async complexity needed | Synchronous workers block during Pandoc subprocess |
| FastAPI + Uvicorn | Async I/O, auto-generated OpenAPI docs | Async subprocess handling adds complexity; no real benefit here since Pandoc call is blocking either way |
| Plain WSGI (no framework) | Fewest dependencies | Too low-level; not worth the boilerplate |
| **GHCR (GitHub Container Registry)** | Free for public repos, native GitHub Actions integration, no extra account | Watchtower needs `/root/.docker/config.json` with GHCR token on the server |
| Docker Hub | Ubiquitous, Watchtower has first-class support | Rate-limited for anonymous pulls; requires separate account |
| **python:3.12-slim + apt pandoc** | Single image, simple Dockerfile, Pandoc version from Debian stable | Pandoc version may lag latest upstream; upgrades require image rebuild |
| Multi-stage build with Pandoc binary download | Pinnable Pandoc version | More complex Dockerfile, curl + sha verification needed |
| **Watchtower (label-enable mode)** | Automatic rolling updates; poll interval configurable | Requires Docker socket mount; GHCR credentials must be present on host |
| Manual `docker compose pull && up -d` | No credentials on server; explicit control | Requires SSH access or CI job per deploy; more operational overhead |

## Decision

- **Flask + Gunicorn** with 2 synchronous workers and 120 s timeout — sufficient for the expected file sizes and single-tenant usage pattern.
- **GHCR** via `ghcr.io/yehiagamalx/pandoc-api` — zero-config with `GITHUB_TOKEN` in Actions, and the server already has Docker credentials infrastructure.
- **python:3.12-slim + apt pandoc** — simplest correct Dockerfile; Pandoc version is stable enough for DOCX conversion.
- **Watchtower in label-enable mode** — only monitors containers explicitly opted-in via label, reducing blast radius.

## Consequences

- Watchtower requires `/root/.docker/config.json` on the VPS with a GHCR personal access token (classic, `read:packages` scope).
- Gunicorn workers are synchronous; large `.docx` files will hold a worker for the duration of the Pandoc call. Acceptable for private/single-consumer usage; revisit if load increases.
- Pandoc version is controlled by the Debian apt mirror; a breaking Pandoc change requires an image rebuild, not just a config change.
- GHCR image is public (repo is public); no secrets are baked into the image.

## Artifacts

- [app.py](../../app.py)
- [Dockerfile](../../Dockerfile)
- [docker-compose.yml](../../docker-compose.yml)
- [.github/workflows/publish.yml](../../.github/workflows/publish.yml)
