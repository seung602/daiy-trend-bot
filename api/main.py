from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.trends import router as trends_router
from api.platforms import router as platforms_router
from api.google import router as google_router
from api.reports import router as reports_router
from api.keywords import router as keywords_router

app.include_router(keywords_router)


app = FastAPI(
    title="K-Beauty Trend Engine API",
    description="K-Beauty Daily Trend Engine Read-Only API",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Routers
# ============================================================

app.include_router(trends_router)
app.include_router(platforms_router)
app.include_router(google_router)
app.include_router(reports_router)


# ============================================================
# Health Check
# ============================================================

@app.get("/")
def root():

    return {
        "status": "ok",
        "service": "K-Beauty Trend Engine API",
        "version": "1.0.0"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }
