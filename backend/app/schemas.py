from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SetupIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    grade: str = "初一"
    role: str = "student"


class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    grade: str = ""
    role: str = "student"  # student | parent


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    grade: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    grade: str = "初一"


class UserUpdate(BaseModel):
    password: Optional[str] = None
    display_name: Optional[str] = None
    grade: Optional[str] = None
    is_active: Optional[bool] = None


class GlobalSettingsIn(BaseModel):
    api_base_url: str = ""
    api_key: str = ""
    chat_model: str = ""
    vision_model: str = ""
    temperature: float = 0.7
    system_extra_prompt: str = ""


class PersonalSettingsIn(BaseModel):
    api_base_url: str = ""
    api_key: str = ""
    chat_model: str = ""
    vision_model: str = ""
    grade: str = ""


class AnalyzeIn(BaseModel):
    subject: str = "数学"
    grade: str = ""
    mode: Literal["single", "batch"] = "single"
    text: str = ""
    my_question: str = ""
    image_ids: list[int] = Field(default_factory=list)


class WrongQuestionUpdate(BaseModel):
    subject: Optional[str] = None
    grade: Optional[str] = None
    unit: Optional[str] = None
    knowledge_points: Optional[list[str]] = None
    difficulty: Optional[str] = None
    question_text: Optional[str] = None
    wrong_reason: Optional[str] = None
    correct_solution: Optional[str] = None
    key_points: Optional[list[str]] = None
    extensions: Optional[str] = None
    mastery: Optional[str] = None
    is_reviewed: Optional[bool] = None


class ConversationCreate(BaseModel):
    title: str = "新对话"
    subject: str = ""
    grade: str = ""
    context_kind: str = ""
    context_ref: str = ""


class ChatMessageIn(BaseModel):
    content: str
    image_ids: list[int] = Field(default_factory=list)


class ProfileIn(BaseModel):
    subject: str
    content: str


class GoalCreate(BaseModel):
    subject: str = ""
    title: str = ""
    question_type: str = ""
    description: str = ""
    reason: str = ""
    due_date: str = ""


class GoalUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None


class MethodCreate(BaseModel):
    subject: str = ""
    knowledge_point: str = ""
    question_type: str = ""
    specific_method: str = ""
    general_method: str = ""


class ScanHomeworkIn(BaseModel):
    subject: str = ""
    grade: str = ""
    image_ids: list[int] = Field(default_factory=list)


class GenericOut(BaseModel):
    ok: bool = True
    data: Any = None
    message: str = ""
