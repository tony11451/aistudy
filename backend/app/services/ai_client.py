"""OpenAI 兼容协议客户端：流式对话、视觉输入、JSON 结构化输出。"""
import base64
import json
import re
from pathlib import Path
from typing import AsyncIterator

import httpx

from ..config import IMAGES_DIR

TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class AIConfigError(Exception):
    pass


class AIClient:
    def __init__(self, base_url: str, api_key: str, chat_model: str,
                 vision_model: str = "", temperature: float = 0.7):
        if not base_url or not api_key or not chat_model:
            raise AIConfigError("AI 接口未配置：请在设置中填写 Base URL、API Key 和模型名")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.vision_model = vision_model or chat_model
        self.temperature = temperature

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def stream_chat(self, messages: list, temperature: float | None = None,
                          model: str = "") -> AsyncIterator[str]:
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", self.endpoint, headers=self._headers(),
                                     json=payload) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", errors="ignore")
                    raise AIConfigError(f"AI 接口返回 {resp.status_code}: {body[:300]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content") or ""
                    if content:
                        yield content

    async def complete(self, messages: list, model: str = "",
                       temperature: float | None = None) -> str:
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(self.endpoint, headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise AIConfigError(f"AI 接口返回 {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIConfigError("AI 接口返回空结果")
        return (choices[0].get("message") or {}).get("content") or ""

    async def complete_json(self, messages: list, model: str = "",
                            temperature: float | None = None):
        text = await self.complete(messages, model=model, temperature=temperature)
        return extract_json(text)


def extract_json(text: str):
    if not text:
        raise ValueError("AI 返回为空")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start_arr, end_arr = text.find("["), text.rfind("]")
    start_obj, end_obj = text.find("{"), text.rfind("}")
    candidates = []
    if start_obj != -1 and end_obj > start_obj:
        candidates.append(text[start_obj:end_obj + 1])
    if start_arr != -1 and end_arr > start_arr:
        candidates.append(text[start_arr:end_arr + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"无法解析 AI 返回的 JSON: {text[:200]}")


def image_to_data_uri(image_id: int, user_id: int) -> str:
    """读取用户上传的图片转 base64 data URI。"""
    path = IMAGES_DIR / f"u{user_id}_{image_id}.jpg"
    if not path.exists():
        path = IMAGES_DIR / f"{image_id}.jpg"
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {image_id}")
    suffix = path.suffix.lower().lstrip(".") or "jpeg"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def build_user_content(text: str, image_ids: list[int], user_id: int,
                       vision: bool = True, max_images: int = 10) -> list | str:
    """构建含图片的 user content；max_images 按模型视觉能力裁剪。"""
    if not image_ids or not vision:
        return text or "请分析。"
    parts: list = []
    if text:
        parts.append({"type": "text", "text": text})
    for iid in image_ids[:max_images]:
        parts.append({"type": "image_url", "image_url": {"url": image_to_data_uri(iid, user_id)}})
    return parts
