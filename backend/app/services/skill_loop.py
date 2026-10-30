"""Skill 调用循环：AI 通过 JSON 协议自由调用技能，读写数据后继续对话。

事件流：("skill", {...}) → ("change", {...}) → ("delta", str) ... → ("final", str)

流式策略（v5）：
- 回答开头疑似技能调用 → 全程缓冲，不外泄 JSON；
- 普通文本 → 滞后 200 字符流式透传（防止中段 skill JSON 漏出）；
  发现中段出现 {"skill" 则截断外发、其余入缓冲；
- 流结束后正则抽取缓冲区中的 skill JSON：剔除显示、执行技能、继续循环，
  环绕的正文文本照常显示。
"""
import json
import re
from typing import AsyncIterator

from sqlalchemy.orm import Session

from ..models import User
from .ai_client import AIClient, extract_json
from .skills import SKILLS, SkillError, execute_skill

MAX_ROUNDS = 8
SKILL_PREFIXES = ('{"skill"', '{"skill_call"', '```')
TAIL_LAG = 200

SKILL_JSON_RE = re.compile(
    r'```(?:json)?\s*(\{[^`]*?"skill"\s*:[^`]*?\})\s*```|'
    r'(\{\s*"skill"\s*:\s*"[^"]+"\s*(?:,\s*"args"\s*:\s*\{.*?\})?\s*\})',
    re.S,
)


def _looks_like_skill(buffer: str) -> bool:
    s = buffer.lstrip()
    return any(s.startswith(p) for p in SKILL_PREFIXES)


def extract_inline_skill_calls(text: str) -> tuple[str, list[dict]]:
    """从任意文本中抽取 skill 调用 JSON；返回 (剔除后的文本, 调用列表)。"""
    calls: list[dict] = []
    pieces = []
    last = 0
    for m in SKILL_JSON_RE.finditer(text):
        raw = m.group(1) or m.group(2) or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        ok = False
        if isinstance(data, dict) and data.get("skill"):
            calls.append(data)
            ok = True
        elif isinstance(data, list) and all(isinstance(d, dict) and d.get("skill") for d in data):
            calls.extend(data)
            ok = True
        if not ok:
            continue
        pieces.append(text[last:m.start()])
        last = m.end()
    pieces.append(text[last:])
    cleaned = re.sub(r'\n{3,}', '\n\n', "".join(pieces)).strip()
    return cleaned, calls


async def _execute_calls(db: Session, user: User, ctx: dict,
                         calls: list[dict]) -> AsyncIterator[tuple[str, object]]:
    """执行一批技能调用，产出 skill/change 事件，最后产出 ("results", payload)。"""
    results_payload = []
    executed = False
    for call in calls[:4]:
        if not isinstance(call, dict):
            continue
        name = call.get("skill") or call.get("name") or ""
        args = call.get("args") or {}
        if name not in SKILLS:
            summary = f"未知技能：{name}"
            results_payload.append({"skill": name, "summary": summary})
            yield ("skill", {"name": name, "status": "error", "summary": summary})
            continue
        yield ("skill", {"name": name, "status": "start", "args": args})
        try:
            result = await execute_skill(db, user, ctx, name, args)
        except Exception as e:
            summary = f"技能执行失败：{e}"
            yield ("skill", {"name": name, "status": "error", "summary": summary})
            results_payload.append({"skill": name, "summary": summary})
            continue
        executed = True
        for change in result.get("changes") or []:
            yield ("change", change)
        summary = result.get("summary", "完成")
        yield ("skill", {"name": name, "status": "done", "summary": summary,
                         "kind": result.get("kind", "read")})
        results_payload.append({"skill": name, "summary": summary, "data": result.get("data")})
    yield ("results", {"payload": results_payload, "executed": executed})


async def skill_chat_stream(client: AIClient, db: Session, user: User,
                            ctx: dict, messages: list,
                            model: str = "") -> AsyncIterator[tuple[str, object]]:
    """驱动多轮技能调用；产出事件元组。"""
    conversation = list(messages)
    for _round in range(MAX_ROUNDS):
        mode = None          # None=待定 / "skill" / "text"
        emitted = ""         # 已外发文本
        tail = ""            # 滞后缓冲
        capture = None       # 中段发现 skill JSON 后的缓冲区

        async for chunk in client.stream_chat(conversation, model=model):
            if capture is not None:
                capture += chunk
                continue
            tail += chunk
            if mode is None:
                stripped = tail.lstrip()
                if _looks_like_skill(tail):
                    mode = "skill"
                    capture = tail
                    tail = ""
                    continue
                if len(stripped) < 24:
                    continue
                mode = "text"
            if mode == "text" and len(tail) > TAIL_LAG:
                safe, tail = tail[:-TAIL_LAG], tail[-TAIL_LAG:]
                idx = safe.find('{"skill"')
                if idx != -1:
                    if safe[:idx]:
                        emitted += safe[:idx]
                        yield ("delta", safe[:idx])
                    capture = safe[idx:] + tail
                    tail = ""
                else:
                    emitted += safe
                    yield ("delta", safe)

        # 流结束：归并
        remainder = (capture or "") + tail
        if mode is None:
            mode = "skill" if _looks_like_skill(remainder) else "text"

        calls: list[dict] = []
        if mode == "skill":
            # 纯技能调用轮（可能被 ``` 包裹或含多调用）
            cleaned, inline = extract_inline_skill_calls(remainder)
            if inline:
                calls = inline
            else:
                try:
                    data = extract_json(remainder)
                    calls = data if isinstance(data, list) else [data]
                except Exception:
                    calls = []
            if not calls:
                # 解析失败：当普通文本处理
                if remainder:
                    emitted += remainder
                    yield ("delta", remainder)
                yield ("final", emitted)
                return
        else:
            # 文本轮：中段可能夹带 skill 调用
            cleaned, inline = extract_inline_skill_calls(remainder)
            if not inline:
                if remainder:
                    emitted += remainder
                    yield ("delta", remainder)
                yield ("final", emitted)
                return
            calls = inline
            if cleaned:
                emitted += cleaned
                yield ("delta", cleaned)

        # 执行技能
        results_payload = []
        executed = False
        async for ev in _execute_calls(db, user, ctx, calls):
            if ev[0] == "results":
                results_payload = ev[1]["payload"]
                executed = ev[1]["executed"]
            else:
                yield ev

        if not executed and not results_payload:
            yield ("final", emitted)
            return

        conversation.append({"role": "assistant", "content": emitted[-2000:] or "（调用技能）"})
        conversation.append({
            "role": "user",
            "content": "[技能执行结果]\n" + json.dumps(results_payload, ensure_ascii=False)[:6000]
                       + "\n\n请基于以上结果继续：若还需要其他数据可继续调用技能，否则直接给出最终回答"
                         "（Markdown 排版，公式用 LaTeX；若做了修改，向学生说明改了什么、为什么）。",
        })

    yield ("delta", "（技能调用轮次已达上限，基于已有信息给出简要总结）")
    yield ("final", "（技能调用轮次已达上限，基于已有信息给出简要总结）")
