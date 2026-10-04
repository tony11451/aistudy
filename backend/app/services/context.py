"""按用户解析 AI 接口配置（全局共享 + 个人覆盖）。"""
from ..models import AppSettings, User
from .ai_client import AIClient


def resolve_ai_config(db, user: User) -> dict:
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    g = row or AppSettings()
    return {
        "api_base_url": (user.api_base_url or g.api_base_url or "").strip(),
        "api_key": (user.api_key or g.api_key or "").strip(),
        "chat_model": (user.chat_model or g.chat_model or "").strip(),
        "vision_model": (user.vision_model or g.vision_model or "").strip(),
        "temperature": g.temperature or 0.7,
        "system_extra_prompt": g.system_extra_prompt or "",
    }


def get_ai_client(db, user: User) -> AIClient:
    cfg = resolve_ai_config(db, user)
    return AIClient(
        base_url=cfg["api_base_url"],
        api_key=cfg["api_key"],
        chat_model=cfg["chat_model"],
        vision_model=cfg["vision_model"],
        temperature=cfg["temperature"],
    )


def get_vision_client(db, user: User) -> AIClient:
    """视觉分析使用 vision_model。"""
    cfg = resolve_ai_config(db, user)
    return AIClient(
        base_url=cfg["api_base_url"],
        api_key=cfg["api_key"],
        chat_model=cfg["vision_model"] or cfg["chat_model"],
        vision_model=cfg["vision_model"] or cfg["chat_model"],
        temperature=0.3,
    )
