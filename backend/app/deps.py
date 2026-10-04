from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization") or ""
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not token:
        token = request.query_params.get("token", "")
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
