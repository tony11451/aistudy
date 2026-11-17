"""智学网集成 API：配置 / Cookie 登录 / 手动同步 / 同步记录。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User, ZhixueAccount, ZhixueSyncRun
from ..services import zhixue as zxw_svc

router = APIRouter(prefix="/api/zhixue", tags=["zhixue"])

BOOKMARKLET = (
    "javascript:(function(){function getCookies(){return document.cookie;}"
    "function copyToClipboard(text){const t=document.createElement('textarea');t.value=text;"
    "document.body.appendChild(t);t.select();document.execCommand('copy');"
    "document.body.removeChild(t);}"
    "const c=getCookies();copyToClipboard(c);alert('Cookies 已复制到剪切板！');})();"
)


def _acc(db: Session, user: User) -> ZhixueAccount:
    acc = db.query(ZhixueAccount).filter(ZhixueAccount.user_id == user.id).first()
    if not acc:
        acc = ZhixueAccount(user_id=user.id)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    return acc


@router.get("")
def get_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _acc(db, user)
    return {
        "enabled": acc.enabled,
        "login_mode": acc.login_mode,
        "status": acc.status,
        "has_cookie": bool(acc.cookie),
        "zxw_username": acc.zxw_username,
        "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
        "last_sync_summary": acc.last_sync_summary,
    }


@router.put("")
def update_config(payload: dict, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    acc = _acc(db, user)
    if "enabled" in payload:
        acc.enabled = bool(payload["enabled"])
    if "login_mode" in payload and payload["login_mode"] in ("cookie", "playwright"):
        acc.login_mode = payload["login_mode"]
    if "zxw_username" in payload:
        acc.zxw_username = str(payload["zxw_username"] or "")[:128]
    db.commit()
    return {"ok": True}


@router.post("/login")
def login_cookie(payload: dict, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    cookie = str(payload.get("cookie") or "").strip()
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie 为空")
    ok, msg = zxw_svc.login_check(cookie)
    acc = _acc(db, user)
    if ok:
        acc.cookie = cookie
        acc.enabled = True
        acc.status = "ok"
    else:
        acc.status = "error"
    db.commit()
    return {"ok": ok, "message": msg}


@router.post("/sync")
def sync(payload: dict, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    scope = str(payload.get("scope") or "all")
    try:
        result = zxw_svc.sync_user(db, user, scope=scope)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:400])
    return {"ok": True, **result}


@router.get("/sync-runs")
def sync_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ZhixueSyncRun).filter(ZhixueSyncRun.user_id == user.id)
            .order_by(ZhixueSyncRun.created_at.desc()).limit(20).all())
    return [{
        "id": r.id, "scope": r.scope, "added": r.added, "updated": r.updated,
        "failed": r.failed, "message": r.message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/tidy")
async def tidy(payload: dict | None = None, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """整理智学网数据：规则清理（免费）+ 可选 AI 深度整理（清洗/补全/判定）。"""
    payload = payload or {}
    acc = _acc(db, user)
    from ..services.zhixue_tidy import ai_tidy_items, tidy_zhixue_data
    try:
        stats = await tidy_zhixue_data(db, user, cookie=acc.cookie or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"整理失败：{e}"[:400])
    if payload.get("ai"):
        try:
            ai_stats = await ai_tidy_items(db, user, cookie=acc.cookie or "")
            stats.update({f"ai_{k}": v for k, v in ai_stats.items()})
        except Exception as e:
            stats["ai_error"] = str(e)[:200]
    return {"ok": True, **stats}


@router.get("/bookmarklet")
def bookmarklet():
    """登录引导：网页端登录智学网后点击书签复制 Cookie。"""
    return {
        "bookmarklet": BOOKMARKLET,
        "guide": [
            "1. 浏览器打开智学网 https://edc.zhixue.com/login.html 并登录",
            "2. 在书签管理器新建书签，名称随意，网址粘贴上面的书签脚本",
            "3. 回到智学网页面点击该书签，Cookie 自动复制到剪贴板",
            "4. 回到本页粘贴 Cookie 并保存",
        ],
    }
