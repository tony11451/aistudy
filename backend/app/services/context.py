"""按用户/供应商解析 AI 配置（供应商体系 + 旧配置兼容）。

模型引用格式："{provider_id}::{model}"；也兼容裸模型名（在各供应商中查找）。
模型条目：{"name", "vision": bool, "max_images": int}（兼容旧字符串条目）。
"""
from sqlalchemy.orm import Session

from ..models import AIProvider, AppSettings, User
from .ai_client import AIClient, AIConfigError


def _norm_models(p: AIProvider) -> list[dict]:
    out = []
    for m in (p.models or []):
        if isinstance(m, dict):
            out.append({
                "name": str(m.get("name") or "").strip(),
                "vision": bool(m.get("vision")),
                "max_images": int(m.get("max_images") or 5),
            })
        else:
            out.append({"name": str(m).strip(), "vision": False, "max_images": 5})
    return [m for m in out if m["name"]]


def _get_row(db: Session) -> AppSettings:
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not row:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def migrate_legacy_models(db: Session) -> None:
    """把旧的 AppSettings.models / 全局 base_url 迁移成供应商（只执行一次）。"""
    row = _get_row(db)
    legacy_models = [m for m in (row.models or []) if m]
    has_provider = db.query(AIProvider).count() > 0
    if has_provider:
        return
    if legacy_models or row.api_base_url:
        p = AIProvider(
            name="默认供应商",
            base_url=row.api_base_url or "",
            api_key=row.api_key or "",
            models=legacy_models or ([row.chat_model] if row.chat_model else []),
        )
        db.add(p)
        db.flush()
        if not row.current_provider_id and p.models:
            row.current_provider_id = p.id
            row.current_model = p.models[0]
    db.commit()


def resolve_provider(db: Session, provider_id: int | None = None) -> AIProvider | None:
    if provider_id:
        return db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    return db.query(AIProvider).filter(AIProvider.is_active.is_(True)).order_by(AIProvider.sort_order).first()


def split_model_ref(ref: str) -> tuple[int | None, str]:
    """'3::deepseek-chat' -> (3, 'deepseek-chat')；裸名 -> (None, name)"""
    ref = (ref or "").strip()
    if "::" in ref:
        pid, model = ref.split("::", 1)
        try:
            return int(pid), model.strip()
        except ValueError:
            return None, ref
    return None, ref


def resolve_model(db: Session, user: User, model_ref: str = "") -> tuple[AIProvider | None, str]:
    """解析出 (供应商, 模型名)。优先级：显式 ref > 个人覆盖 > 全局当前模型 > 首个可用。"""
    if model_ref:
        pid, model = split_model_ref(model_ref)
        if pid:
            p = db.query(AIProvider).filter(AIProvider.id == pid).first()
            if p:
                names = [m["name"] for m in _norm_models(p)]
                return p, model or (names[0] if names else "")
        else:
            for p in db.query(AIProvider).filter(AIProvider.is_active.is_(True)).all():
                if model in [m["name"] for m in _norm_models(p)]:
                    return p, model
    # 个人覆盖（保留旧能力）
    if user.api_base_url and user.api_key:
        p = AIProvider(name="personal", base_url=user.api_base_url,
                       api_key=user.api_key,
                       models=[{"name": user.chat_model, "vision": True, "max_images": 5}]
                       if user.chat_model else [])
        return p, user.chat_model
    row = _get_row(db)
    if row.current_provider_id and row.current_model:
        p = db.query(AIProvider).filter(AIProvider.id == row.current_provider_id).first()
        if p:
            return p, row.current_model
    # 兜底：首个活跃供应商的首个模型
    p = resolve_provider(db)
    if p:
        names = [m["name"] for m in _norm_models(p)]
        return p, (names[0] if names else "")
    # 兼容旧版：直接用全局 base_url/key/chat_model
    if row.api_base_url and row.api_key and row.chat_model:
        legacy = AIProvider(name="global-legacy", base_url=row.api_base_url,
                            api_key=row.api_key,
                            models=[{"name": row.chat_model, "vision": True, "max_images": 5}])
        return legacy, row.chat_model
    return None, ""


def _model_caps(p: AIProvider | None, model: str) -> dict:
    if not p:
        return {"vision": False, "max_images": 5}
    for m in _norm_models(p):
        if m["name"] == model:
            return m
    return {"vision": False, "max_images": 5}


def get_ai_client(db: Session, user: User, model_ref: str = "") -> AIClient:
    provider, model = resolve_model(db, user, model_ref)
    if not provider or not model:
        raise AIConfigError("尚未配置可用模型：请在「设置 → 供应商」添加供应商与模型")
    caps = _model_caps(provider, model)
    client = AIClient(
        base_url=provider.base_url,
        api_key=provider.api_key,
        chat_model=model,
        vision_model=model,
        temperature=_get_row(db).temperature or 0.7,
    )
    client.max_images = caps["max_images"]
    client.supports_vision = caps["vision"]
    return client


def get_vision_client(db: Session, user: User, model_ref: str = "") -> AIClient:
    """图片任务自动路由到「支持视觉」的模型；无可用则报错提示配置。"""
    provider, model = resolve_model(db, user, model_ref)
    caps = _model_caps(provider, model)
    if provider and caps["vision"]:
        client = get_ai_client(db, user, model_ref)
        return client
    # 当前模型不支持视觉 → 找任意供应商的视觉模型
    for p in db.query(AIProvider).filter(AIProvider.is_active.is_(True)).all():
        for m in _norm_models(p):
            if m["vision"]:
                client = AIClient(
                    base_url=p.base_url, api_key=p.api_key,
                    chat_model=m["name"], vision_model=m["name"],
                    temperature=_get_row(db).temperature or 0.7,
                )
                client.max_images = m["max_images"]
                client.supports_vision = True
                return client
    raise AIConfigError(
        "图片任务需要支持视觉的模型：请在「设置 → 供应商」为某个模型勾选「支持视觉」"
        "（如 GLM-4V、Qwen-VL、MiMo-VL 等）")


def current_model_ref(db: Session, user: User) -> str:
    provider, model = resolve_model(db, user)
    if provider and model:
        return f"{provider.id}::{model}"
    return ""


def resolve_ai_config(db: Session, user: User) -> dict:
    """兼容旧接口：返回当前生效配置摘要。"""
    provider, model = resolve_model(db, user)
    row = _get_row(db)
    return {
        "api_base_url": provider.base_url if provider else "",
        "chat_model": model,
        "vision_model": model,
        "temperature": row.temperature or 0.7,
        "has_key": bool(provider and provider.api_key),
        "system_extra_prompt": row.system_extra_prompt or "",
    }
