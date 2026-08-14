from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.trends import router as trends_router
from api.platforms import router as platforms_router
from api.google import router as google_router
from api.reports import router as reports_router
from api.dashboard import router as dashboard_router
from api.ksignal import router as ksignal_router


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="K-Beauty Trend Intelligence",
    description="Read-only dashboard — K-Signal ranking first, Western signals secondary",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ksignal_router)
app.include_router(trends_router)
app.include_router(platforms_router)
app.include_router(google_router)
app.include_router(reports_router)
app.include_router(dashboard_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "status": "ok",
        "service": "K-Beauty Trend Intelligence",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
