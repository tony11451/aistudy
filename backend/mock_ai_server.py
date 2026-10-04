"""独立 mock OpenAI 兼容服务，用于本地联调：python mock_ai_server.py [port]"""
import json
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    system = body["messages"][0]["content"]
    user_last = body["messages"][-1]["content"]
    text = user_last if isinstance(user_last, str) else json.dumps(user_last, ensure_ascii=False)

    if "错题分析导师" in system:
        answer = json.dumps({
            "question_text": "解方程 x^2-5x+6=0", "subject": "数学",
            "unit": "一元二次方程", "knowledge_points": ["因式分解"],
            "difficulty": "中等", "wrong_reason": "因式分解时符号弄反了",
            "correct_solution": "1. (x-2)(x-3)=0\n2. x=2 或 x=3",
            "key_points": ["注意符号"], "extensions": "变式训练",
            "learning_content": "一元二次方程解法",
            "method": {"specific": "先判别式", "general": "先化标准型"},
        }, ensure_ascii=False)
    elif "逐题识别" in system:
        answer = json.dumps([{"question_text": "题1", "knowledge_points": ["k1"],
                              "wrong_reason": "r", "correct_solution": "s"}], ensure_ascii=False)
    elif "学习档案管理员" in system:
        answer = "薄弱点：因式分解符号易错；建议强化基础训练。"
    elif "正在学习什么" in system:
        answer = json.dumps({
            "learning_items": [{"knowledge_point": "一元二次方程", "unit": "一元二次方程",
                                "learning_state": "learning", "evidence": "作业多为该章节"}],
            "summary": "正在学习一元二次方程解法"}, ensure_ascii=False)
    elif "刷题规划师" in system:
        answer = json.dumps([{"subject": "数学", "title": "专攻因式分解",
                              "question_type": "因式分解", "description": "每天10题",
                              "reason": "错题集中", "due_date": "本周日"}], ensure_ascii=False)
    elif "答题方法教练" in system:
        answer = json.dumps({"specific_method": "先看设问", "general_method": "是什么-为什么-怎么做",
                             "knowledge_point": "材料题", "question_type": "材料分析"}, ensure_ascii=False)
    elif "学习分析师" in system:
        answer = "# 学习报告\n- 进步明显\n- 下一步：每天10题"
    else:
        answer = "这是关于「" + text[:20] + "」的详细讲解。第一步先理解概念，第二步再练题。"

    if body.get("stream"):
        async def gen():
            for i in range(0, len(answer), 16):
                chunk = {"choices": [{"delta": {"content": answer[i:i + 16]}}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return {"choices": [{"message": {"content": answer}}]}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
