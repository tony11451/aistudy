from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    grade: Mapped[str] = mapped_column(String(16), default="初一")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # personal API override (empty = use global)
    api_base_url: Mapped[str] = mapped_column(String(256), default="")
    api_key: Mapped[str] = mapped_column(String(256), default="")
    chat_model: Mapped[str] = mapped_column(String(128), default="")
    vision_model: Mapped[str] = mapped_column(String(128), default="")
    subjects: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_base_url: Mapped[str] = mapped_column(String(256), default="")
    api_key: Mapped[str] = mapped_column(String(256), default="")
    chat_model: Mapped[str] = mapped_column(String(128), default="")
    vision_model: Mapped[str] = mapped_column(String(128), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    system_extra_prompt: Mapped[str] = mapped_column(Text, default="")
    models: Mapped[list] = mapped_column(JSON, default=list)
    model_assign: Mapped[dict] = mapped_column(JSON, default=dict)


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), default="数学", index=True)
    grade: Mapped[str] = mapped_column(String(16), default="", index=True)
    unit: Mapped[str] = mapped_column(String(64), default="")
    knowledge_points: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(16), default="中等")
    question_text: Mapped[str] = mapped_column(Text, default="")
    wrong_reason: Mapped[str] = mapped_column(Text, default="")
    correct_solution: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    extensions: Mapped[str] = mapped_column(Text, default="")
    method_specific: Mapped[str] = mapped_column(Text, default="")
    method_general: Mapped[str] = mapped_column(Text, default="")
    learning_content: Mapped[str] = mapped_column(String(128), default="")
    analysis_raw: Mapped[dict] = mapped_column(JSON, default=dict)
    images: Mapped[list] = mapped_column(JSON, default=list)
    original_images: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default="photo")  # photo | text | batch
    my_question: Mapped[str] = mapped_column(Text, default="")
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    mastery: Mapped[str] = mapped_column(String(16), default="weak")  # weak|improving|mastered
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StudyProfile(Base):
    __tablename__ = "study_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeNode(Base):
    """统一节点树：学科 → 大方向知识点 → 二级子节点 / 弱点（每人一棵树）"""

    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_nodes.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    node_type: Mapped[str] = mapped_column(String(16), default="knowledge")  # knowledge | weakness
    confidence: Mapped[str] = mapped_column(String(16), default="suspected")  # suspected | confirmed
    mastery: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown|weak|improving|mastered
    learning_state: Mapped[str] = mapped_column(String(16), default="not_started")  # not_started|learning|learned
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | manual | chat_summary
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    subject: Mapped[str] = mapped_column(String(32), default="")
    grade: Mapped[str] = mapped_column(String(16), default="")
    context_kind: Mapped[str] = mapped_column(String(16), default="")  # "" | knowledge | wrong_question
    context_ref: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    images: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PracticeGoal(Base):
    __tablename__ = "practice_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(128), default="")
    question_type: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | done | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[str] = mapped_column(String(32), default="")


class MethodCard(Base):
    __tablename__ = "method_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), default="", index=True)
    knowledge_point: Mapped[str] = mapped_column(String(64), default="")
    question_type: Mapped[str] = mapped_column(String(64), default="")
    specific_method: Mapped[str] = mapped_column(Text, default="")
    general_method: Mapped[str] = mapped_column(Text, default="")
    source_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="manual")  # manual | weekly
    title: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
