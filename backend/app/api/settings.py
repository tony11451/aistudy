from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import AppSettings, User
from ..schemas import GlobalSettingsIn, PersonalSettingsIn
from ..services.context import current_model_ref, resolve_ai_config

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_SUBJECTS = ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治"]


def _get_row(db: Session) -> AppSettings:
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not row:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 8 + key[-4:]


@router.get("")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = resolve_ai_config(db, user)
    row = _get_row(db)
    assign = row.model_assign or {}
    return {
        "effective": {
            "api_base_url": cfg["api_base_url"],
            "chat_model": cfg["chat_model"],
            "vision_model": cfg["vision_model"],
            "temperature": cfg["temperature"],
            "has_key": bool(cfg.get("has_key")),
        },
        "global": {
            "api_base_url": row.api_base_url,
            "api_key_masked": _mask(row.api_key),
            "has_key": bool(row.api_key),
            "chat_model": row.chat_model,
            "vision_model": row.vision_model,
            "temperature": row.temperature,
            "system_extra_prompt": row.system_extra_prompt,
        },
        "personal": {
            "api_base_url": user.api_base_url,
            "api_key_masked": _mask(user.api_key),
            "has_key": bool(user.api_key),
            "chat_model": user.chat_model,
            "vision_model": user.vision_model,
            "grade": user.grade,
        },
        "models": row.models or [],
        "assign": {
            "chat": assign.get("chat", row.chat_model),
            "vision": assign.get("vision", row.vision_model),
            "analysis": assign.get("analysis", row.chat_model),
        },
        "current_model_ref": current_model_ref(db, user),
        "subjects": user.subjects if user.subjects is not None else DEFAULT_SUBJECTS,
    }


@router.put("/global")
def update_global(payload: GlobalSettingsIn, _: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    row = _get_row(db)
    row.api_base_url = payload.api_base_url.strip()
    if payload.api_key and not payload.api_key.startswith("***") and "*" not in payload.api_key[:6]:
        row.api_key = payload.api_key.strip()
    row.chat_model = payload.chat_model.strip()
    row.vision_model = payload.vision_model.strip()
    row.temperature = payload.temperature
    row.system_extra_prompt = payload.system_extra_prompt
    db.commit()
    return {"ok": True}


@router.put("/personal")
def update_personal(payload: PersonalSettingsIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    user.api_base_url = payload.api_base_url.strip()
    if payload.api_key and "*" not in payload.api_key[:6]:
        user.api_key = payload.api_key.strip()
    user.chat_model = payload.chat_model.strip()
    user.vision_model = payload.vision_model.strip()
    if payload.grade:
        user.grade = payload.grade
    db.commit()
    return {"ok": True}


@router.put("/models")
def update_models(payload: dict, _: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    row = _get_row(db)
    models = [m.strip() for m in (payload.get("models") or []) if m.strip()]
    row.models = models[:30]
    assign = payload.get("assign") or {}
    row.model_assign = {
        "chat": assign.get("chat", ""),
        "vision": assign.get("vision", ""),
        "analysis": assign.get("analysis", ""),
    }
    db.commit()
    return {"ok": True, "models": row.models}


@router.put("/subjects")
def update_subjects(payload: dict, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    subjects = [s.strip() for s in (payload.get("subjects") or []) if s.strip()]
    user.subjects = subjects[:20]
    db.commit()
    return {"ok": True, "subjects": user.subjects}


@router.get("/nightly")
def get_nightly(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_row(db)
    return {"nightly_time": row.nightly_time or "23:00",
            "nightly_enabled": row.nightly_enabled,
            "nightly_last_run": row.nightly_last_run}


@router.put("/nightly")
def update_nightly(payload: dict, _: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    row = _get_row(db)
    if "nightly_time" in payload:
        t = str(payload.get("nightly_time") or "23:00")
        try:
            hh, mm = t.split(":")
            int(hh), int(mm)
            row.nightly_time = t[:8]
        except Exception:
            raise HTTPException(status_code=400, detail="时间格式应为 HH:MM")
    if "nightly_enabled" in payload:
        row.nightly_enabled = bool(payload["nightly_enabled"])
    db.commit()
    return {"ok": True}
