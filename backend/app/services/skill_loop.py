"""Skill 调用循环：AI 通过 JSON 协议自由调用技能，读写数据后继续对话。

事件流：("skill", {...}) → ("change", {...}) → ("delta", str) ... → ("final", str)
流式缓冲策略：若回答开头像技能调用 JSON 则暂扣不发，否则按普通文本流式透传。
"""
import json
from typing import AsyncIterator

from sqlalchemy.orm import Session

from ..models import User
from .ai_client import AIClient, extract_json
from .skills import SKILLS, SkillError, execute_skill

MAX_ROUNDS = 8
SKILL_PREFIXES = ('{"skill"', '{"skill_call"', '```')


def _looks_like_skill(buffer: str) -> bool:
    s = buffer.lstrip()
    return any(s.startswith(p) for p in SKILL_PREFIXES)


async def skill_chat_stream(client: AIClient, db: Session, user: User,
                            ctx: dict, messages: list,
                            model: str = "") -> AsyncIterator[tuple[str, object]]:
    """驱动多轮技能调用；产出事件元组。"""
    conversation = list(messages)
    for _round in range(MAX_ROUNDS):
        buffer = ""
        mode = None  # None=待定 / "skill" / "text"
        full_text = ""
        async for chunk in client.stream_chat(conversation, model=model):
            buffer += chunk
            if mode is None:
                stripped = buffer.lstrip()
                if _looks_like_skill(buffer):
                    mode = "skill"
                elif len(stripped) >= 24:
                    mode = "text"
                    full_text += buffer
                    yield ("delta", buffer)
                    buffer = ""
            elif mode == "text":
                full_text += chunk
                yield ("delta", chunk)

        if mode is None:
            # 短回答：当作普通文本
            mode = "text"
            if buffer:
                full_text += buffer
                yield ("delta", buffer)
            buffer = ""

        if mode == "text":
            yield ("final", full_text)
            return

        # —— 技能调用轮 ——
        try:
            data = extract_json(buffer)
        except Exception:
            # 不是合法 JSON，退回普通文本
            yield ("delta", buffer)
            yield ("final", buffer)
            return

        if isinstance(data, list):
            calls = data
        else:
            calls = [data]

        executed_any = False
        results_payload = []
        for call in calls[:4]:
            if not isinstance(call, dict):
                continue
            name = call.get("skill") or call.get("name") or ""
            args = call.get("args") or {}
            if name not in SKILLS:
                results_payload.append({"skill": name, "summary": f"未知技能：{name}"})
                yield ("skill", {"name": name, "status": "error", "summary": f"未知技能：{name}"})
                continue
            yield ("skill", {"name": name, "status": "start", "args": args})
            try:
                result = execute_skill(db, user, ctx, name, args)
            except SkillError as e:
                result = {"skill": name, "summary": f"技能执行失败：{e}", "kind": SKILLS[name]["kind"]}
                yield ("skill", {"name": name, "status": "error", "summary": result["summary"]})
                results_payload.append({"skill": name, "summary": result["summary"]})
                continue
            except Exception as e:
                result = {"skill": name, "summary": f"技能异常：{e}", "kind": SKILLS[name]["kind"]}
                yield ("skill", {"name": name, "status": "error", "summary": result["summary"]})
                results_payload.append({"skill": name, "summary": result["summary"]})
                continue
            executed_any = True
            for change in result.get("changes") or []:
                yield ("change", change)
            summary = result.get("summary", "完成")
            yield ("skill", {"name": name, "status": "done", "summary": summary,
                             "kind": result.get("kind", "read")})
            results_payload.append({
                "skill": name,
                "summary": summary,
                "data": result.get("data"),
            })

        if not executed_any and not results_payload:
            # 全部失败：把原始内容当文本返回
            yield ("delta", buffer)
            yield ("final", buffer)
            return

        conversation.append({"role": "assistant", "content": buffer})
        conversation.append({
            "role": "user",
            "content": "[技能执行结果]\n" + json.dumps(results_payload, ensure_ascii=False)[:6000]
                       + "\n\n请基于以上结果继续：若还需要其他数据可继续调用技能，否则直接给出最终回答。",
        })

    # 轮次用尽：强制收尾
    yield ("delta", "（技能调用轮次已达上限，基于已有信息给出简要总结）")
    yield ("final", "（技能调用轮次已达上限，基于已有信息给出简要总结）")
