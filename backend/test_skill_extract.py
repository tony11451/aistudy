"""skill_loop 抽取逻辑单元测试（中段/前置/包裹/误伤/多调用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

from app.services.skill_loop import extract_inline_skill_calls  # noqa: E402

# 1) 中段夹带
t1 = '你好！我先看看档案。\n{"skill": "read_profile", "args": {"subject": "数学"}}\n你想聊哪科？'
clean, calls = extract_inline_skill_calls(t1)
assert calls and calls[0]["skill"] == "read_profile", calls
assert "read_profile" not in clean and "你好" in clean and "你想聊哪科" in clean, repr(clean)
print("PASS mid-text")

# 2) 无参数调用
t2 = '前文\n{"skill": "read_progress"}\n后文'
clean2, calls2 = extract_inline_skill_calls(t2)
assert calls2 and calls2[0]["skill"] == "read_progress"
assert "前文" in clean2 and "后文" in clean2
print("PASS no-args")

# 3) ```json 包裹
t3 = '结论如下\n```json\n{"skill": "update_node", "args": {"node_id": 3, "mastery": "weak"}}\n```\n完成。'
clean3, calls3 = extract_inline_skill_calls(t3)
assert calls3 and calls3[0]["args"]["node_id"] == 3, calls3
assert "update_node" not in clean3 and "结论" in clean3 and "完成" in clean3
print("PASS fenced")

# 4) 纯净文本无误伤
t4 = '这是一个 {"skill": 不完整 的例子 { 不是 json'
clean4, calls4 = extract_inline_skill_calls(t4)
assert not calls4 and clean4 == t4.strip(), (calls4, clean4)
print("PASS no-false-positive")

# 5) 多个调用
t5 = 'A{"skill": "read_mindmap"}B{"skill": "read_goals"}C'
clean5, calls5 = extract_inline_skill_calls(t5)
assert len(calls5) == 2, calls5
assert clean5.replace("\n", "") == "ABC", repr(clean5)
print("PASS multi-calls")

print("=== extract tests 5/5 passed ===")
