# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.trends import router as trends_router
from api.platforms import router as platforms_router
from api.reports import router as reports_router

app = FastAPI(
    title="K-Beauty Trend Engine API",
    description="main_kbeauty_final.py 기반 데이터 읽기 전용 API",
    version="1.0.0"
)

# 프론트엔드(React, WebUI 등)에서 접속 허용을 위한 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(trends_router)
app.include_router(platforms_router)
app.include_router(reports_router)

@app.get("/")
def root():
    return {"message": "K-Beauty Trend API Server Running Ready"}

