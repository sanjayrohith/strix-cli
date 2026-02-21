"""
Strix backend API – FastAPI app serving on port 8000.

Run with:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

Your React frontend (on port 8080) calls these endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import analyzer, generator

app = FastAPI(title="Strix Ready API", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS – allow the React frontend to call this API
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to ["http://localhost:8080"] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Scan endpoint – consumed by the React frontend
# ---------------------------------------------------------------------------

@app.post("/scan")
async def scan(request: Request):
    """Clone a GitHub repo, analyse it, generate Docker artifacts.

    **Request body (JSON):**

    ```json
    {
      "url": "https://github.com/owner/repo",
      "os": "linux"
    }
    ```

    **Response (JSON):**

    ```json
    {
      "profile": { ... },
      "artifacts": {
        "Dockerfile": "...",
        "docker-compose.dev.yml": "...",
        ".env.example": "...",
        "PROJECT.md": "..."
      }
    }
    ```
    """
    body = await request.json()
    url = body.get("url", "").strip()
    user_os = body.get("os", "linux").strip().lower()
    if not url:
        return JSONResponse({"detail": "url is required"}, status_code=400)

    try:
        profile = analyzer.analyze_repo(url, user_os=user_os)
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"detail": f"Clone/analysis failed: {exc}"}, status_code=500)

    artifacts = generator.generate(profile)

    # Write artifacts into the cloned repo
    local_path = profile.get("local_path")
    if local_path:
        generator.write_artifacts(local_path, artifacts)

    return {"profile": profile, "artifacts": artifacts}
