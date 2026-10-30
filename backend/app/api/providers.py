"""供应商与模型管理 API。模型条目：{"name", "vision": bool, "max_images": int}。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import AIProvider, AppSettings, User
from ..services.context import current_model_ref, migrate_legacy_models

router = APIRouter(prefix="/api/providers", tags=["providers"])


def normalize_models(models, vision_names=None, max_images=5) -> list[dict]:
    """接受 [str|dict] 与视觉名单，输出规范 dict 列表。"""
    vision_set = {v.strip() for v in (vision_names or []) if v.strip()}
    out = []
    for m in models or []:
        if isinstance(m, dict):
            entry = {
                "name": str(m.get("name") or "").strip(),
                "vision": bool(m.get("vision")),
                "max_images": int(m.get("max_images") or max_images),
            }
        else:
            name = str(m).strip()
            entry = {"name": name, "vision": name in vision_set,
                     "max_images": max_images}
        if entry["name"]:
            out.append(entry)
    return out[:30]


def model_names(p: AIProvider) -> list[str]:
    return [m["name"] if isinstance(m, dict) else str(m) for m in (p.models or [])]


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 8 + key[-4:]


def _serialize(p: AIProvider) -> dict:
    models = normalize_models(p.models)
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "api_key_masked": _mask(p.api_key),
        "has_key": bool(p.api_key),
        "models": models,
        "model_names": [m["name"] for m in models],
        "vision_models": [m["name"] for m in models if m["vision"]],
        "is_active": p.is_active,
        "sort_order": p.sort_order,
    }


@router.get("")
def list_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    migrate_legacy_models(db)
    rows = db.query(AIProvider).order_by(AIProvider.sort_order, AIProvider.id).all()
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return {
        "providers": [_serialize(p) for p in rows],
        "current_model_ref": current_model_ref(db, user),
        "current_provider_id": row.current_provider_id if row else None,
        "current_model": row.current_model if row else "",
    }


@router.post("")
def create_provider(payload: dict, _: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    if not name or not base_url:
        raise HTTPException(status_code=400, detail="缺少名称或 Base URL")
    models = normalize_models(payload.get("models"),
                              payload.get("vision_models"),
                              int(payload.get("max_images") or 5))
    p = AIProvider(
        name=name[:64], base_url=base_url[:256],
        api_key=(payload.get("api_key") or "").strip()[:256],
        models=models,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    # 首个供应商自动设为当前
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if row and not row.current_provider_id and p.models:
        row.current_provider_id = p.id
        row.current_model = model_names(p)[0]
        db.commit()
    return _serialize(p)


@router.put("/{pid}")
def update_provider(pid: int, payload: dict, _: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    p = db.query(AIProvider).filter(AIProvider.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if "name" in payload:
        p.name = str(payload["name"] or p.name)[:64]
    if "base_url" in payload:
        p.base_url = str(payload["base_url"] or p.base_url)[:256]
    if payload.get("api_key") and "*" not in str(payload["api_key"])[:6]:
        p.api_key = str(payload["api_key"]).strip()[:256]
    if "models" in payload:
        p.models = normalize_models(payload.get("models"),
                                    payload.get("vision_models"),
                                    int(payload.get("max_images") or 5))
    if "is_active" in payload:
        p.is_active = bool(payload["is_active"])
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.delete("/{pid}")
def delete_provider(pid: int, _: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    p = db.query(AIProvider).filter(AIProvider.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    db.delete(p)
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if row and row.current_provider_id == pid:
        row.current_provider_id = None
        row.current_model = ""
    db.commit()
    return {"ok": True}


@router.put("/current/model")
def set_current_model(payload: dict, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """设置全局当前模型（ref 格式 provider_id::model）。"""
    ref = str(payload.get("model_ref") or "")
    if "::" not in ref:
        raise HTTPException(status_code=400, detail="模型引用格式应为 provider_id::model")
    pid, model = ref.split("::", 1)
    p = db.query(AIProvider).filter(AIProvider.id == int(pid)).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    row.current_provider_id = p.id
    row.current_model = model.strip()
    db.commit()
    return {"ok": True, "current_model_ref": ref}
