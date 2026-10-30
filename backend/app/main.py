from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, changes, chat, data, knowledge, library, providers, settings, wrong_questions
from .config import IMAGES_DIR
from .database import Base, engine, SessionLocal
from .models import AppSettings

app = FastAPI(title="AI 错题本 · 学习助手", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(providers.router)
app.include_router(changes.router)
app.include_router(data.router)
app.include_router(wrong_questions.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(library.router)


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(AppSettings).filter(AppSettings.id == 1).first():
            db.add(AppSettings(id=1))
            db.commit()
        from .services.context import migrate_legacy_models
        migrate_legacy_models(db)
    finally:
        db.close()


init_db()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/images/{name}")
def get_image(name: str):
    safe = Path(name).name
    path = IMAGES_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path)


# 前端静态资源（构建产物位于 frontend/dist）
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
