from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas import LoginIn, RegisterIn, SetupIn, TokenOut, UserCreate, UserOut, UserUpdate
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    total = db.query(User).count()
    return {"need_setup": total == 0}


@router.post("/setup", response_model=TokenOut)
def setup(payload: SetupIn, db: Session = Depends(get_db)):
    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="系统已初始化")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        grade=payload.grade or "初一",
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"access_token": token, "user": _user_dict(user)}


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).count() == 0:
        raise HTTPException(status_code=400, detail="请先初始化管理员账号")
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    role = payload.role if payload.role in ("student", "parent") else "student"
    grade = payload.grade if role == "student" else ""
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or username,
        grade=grade,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"access_token": token, "user": _user_dict(user)}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    token = create_access_token(user.id, user.username, user.role)
    return {"access_token": token, "user": _user_dict(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


@router.post("/grade-up")
async def grade_up(payload: dict, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """升年级：学年总结 + 旧内容归档 + 新年级学科（需求 11）。"""
    new_grade = str(payload.get("new_grade") or "").strip()
    if new_grade not in ("初一", "初二", "初三", "高一", "高二", "高三"):
        raise HTTPException(status_code=400, detail="年级无效")
    from ..services.grade import grade_up as do_grade_up
    try:
        result = await do_grade_up(
            db, user, new_grade,
            new_subjects=payload.get("subjects"),
            keep_weak=bool(payload.get("keep_weak")),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"升级失败：{e}")
    return {"ok": True, **result}


@router.get("/grade-options")
def grade_options(user: User = Depends(get_current_user)):
    from ..services.grade import NEXT_GRADE, suggested_subjects
    nxt = NEXT_GRADE.get(user.grade or "")
    return {
        "current_grade": user.grade,
        "next_grade": nxt,
        "next_subjects": suggested_subjects(nxt) if nxt else [],
    }


@router.put("/widgets")
def update_widgets(payload: dict, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """首页小组件配置（v6）：启用/排序。"""
    widgets = [str(w) for w in (payload.get("widgets") or []) if w]
    user.widgets = widgets[:12]
    db.commit()
    return {"ok": True, "widgets": user.widgets}


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "grade": user.grade,
        "widgets": user.widgets or [],
        "identity": {"admin": "管理员", "student": "学生", "parent": "家长"}.get(user.role, "学生"),
    }


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, _: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username.strip()).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        grade=payload.grade,
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, _: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.grade is not None:
        user.grade = payload.grade
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user
