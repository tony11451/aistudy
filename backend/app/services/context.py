"""按用户/供应商解析 AI 配置（供应商体系 + 旧配置兼容）。

模型引用格式："{provider_id}::{model}"；也兼容裸模型名（在各供应商中查找）。
"""
from sqlalchemy.orm import Session

from ..models import AIProvider, AppSettings, User
from .ai_client import AIClient, AIConfigError


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
                return p, model or (p.models[0] if p.models else "")
        else:
            for p in db.query(AIProvider).filter(AIProvider.is_active.is_(True)).all():
                if model in (p.models or []):
                    return p, model
    # 个人覆盖（保留旧能力）
    if user.api_base_url and user.api_key:
        p = AIProvider(name="personal", base_url=user.api_base_url,
                       api_key=user.api_key,
                       models=[user.chat_model] if user.chat_model else [])
        return p, user.chat_model
    row = _get_row(db)
    if row.current_provider_id and row.current_model:
        p = db.query(AIProvider).filter(AIProvider.id == row.current_provider_id).first()
        if p:
            return p, row.current_model
    # 兜底：首个活跃供应商的首个模型
    p = resolve_provider(db)
    if p:
        return p, (p.models[0] if p.models else [])
    # 兼容旧版：直接用全局 base_url/key/chat_model
    if row.api_base_url and row.api_key and row.chat_model:
        legacy = AIProvider(name="global-legacy", base_url=row.api_base_url,
                            api_key=row.api_key, models=[row.chat_model])
        return legacy, row.chat_model
    return None, ""


def get_ai_client(db: Session, user: User, model_ref: str = "") -> AIClient:
    provider, model = resolve_model(db, user, model_ref)
    if not provider or not model:
        raise AIConfigError("尚未配置可用模型：请在「设置 → 供应商」添加供应商与模型")
    return AIClient(
        base_url=provider.base_url,
        api_key=provider.api_key,
        chat_model=model,
        vision_model=model,
        temperature=_get_row(db).temperature or 0.7,
    )


def get_vision_client(db: Session, user: User, model_ref: str = "") -> AIClient:
    """图片识别跟随当前选中模型（按产品决策）。"""
    return get_ai_client(db, user, model_ref)


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
