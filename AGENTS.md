# AGENTS.md

AI 学习助手（FastAPI + React，Docker/NAS 部署）。改代码前先看 README 与 `docs/REQUIREMENTS.md`（需求核对表）。

## 环境怪癖（Windows PowerShell，必读，否则反复踩坑）

- `npm` 的 ps1 shim 被执行策略拦截 → 一律用 **`npm.cmd`**；同理 esbuild 用 `esbuild.cmd` 或直接 `npm.cmd run test:render`
- **不要用 `python -c "..."` 内联脚本**（含中文/引号/花括号几乎必被 PowerShell 解析炸掉）→ 写临时 `xxx.py` 文件执行，用完删除（历史上多次踩坑）
- 控制台是 GBK：`Get-Content`/print 中文显示乱码是显示问题不是数据问题；验证内容用 python 读 `encoding='utf-8'`

## 测试

后端（从 `backend/` 目录跑，每个文件自带 `DATA_DIR=tempdir`，可单独跑）：

```bash
cd backend
python smoke_test.py        # 接口冒烟（40）
python mock_ai_test.py      # AI 管线/技能/供应商/搜索（63，内嵌 mock AI @18901）
python e2e_library.py       # 档案库（17）
python e2e_v3.py / e2e_v4.py / e2e_v6.py   # 综合/v6 教研组·智学网mock·整理（46）
python test_skill_extract.py
```

前端：`cd frontend && npm.cmd run build && npm.cmd run test:render`（SSR 渲染冒烟）

- **测试端口一律用 18xxx**（Windows WINNAT 动态排除 8000/8901 等区间，会随机变）
- **SQLite WAL + 长事务坑**：测试里 API 调用（独立会话）修改数据后，本地 `db` 会话不 `rollback()` 就查询会读到旧快照 → 跨会话验证前 `db.rollback()`
- mock_ai_test 的 mock 分支按 system prompt 关键词路由；改 prompts 时确认不会误触发其它分支
- 行为规则变更（如弱点节奏 ≥3 次跨 3 天）→ 更新对应测试断言，别改回行为

## 架构要点（文件名看不出来的）

- **Skill 体系 = AI 读写数据的唯一通道**：`services/skills.py` 注册表（35 技能：name/kind/read|write/executor）+ `services/skill_loop.py` JSON 协议调用循环（`{"skill","args"}`，不依赖 function-calling，任意 OpenAI 兼容接口可用）。新增能力 = 注册表加条目 + executor +（写技能必加 change_log）
- **写技能必须记变更**（`record_change`，before/after 快照）→ 变更卡/撤销/夜审都依赖它；`api/changes.py::undo_change_record` 需同步支持新 target_type
- `main.py::ensure_columns()` 启动时自动补列（models.py 加字段后旧库无缝升级，**不需要手写迁移**，但也别删这个函数）
- **教研组**（`services/teachers.py`）：每科老师常驻流（`Conversation.kind='teacher'`），滚动压缩存 `ConversationSummary`；老师系统提示词 = 图谱+档案+教研记录+压缩摘要（长期记忆不受压缩影响）
- **智学网**（`services/zhixue.py`）：`zhixuewang` SDK 签名易错——`get_original(学科, 考试)` 双参、`get_errorbook(exam_id, subject_id)` 传 ID 不传对象；改前先读 `site-packages/zhixuewang/student/student.py`；图片下载必须带 Cookie+Referer
- 模型解析链在 `services/context.py`：`provider_id::model` 引用 → 个人覆盖 → 全局当前 → 首个供应商 → 旧全局兜底；图片任务用 `get_vision_client`（自动路由支持视觉的模型）
- 提示词集中在 `app/prompts.py`；输出格式约定：Markdown + LaTeX（`$..$`）+ `##` 板块（前端渲染为卡片）+ 技能 JSON 必须单独成行

## 构建与部署

- **镜像源**：Dockerfile `FROM` 直连 `docker.1ms.run/...`（NAS 会劫持 docker.io 至失效加速器）；pip 清华源；`frontend/.npmrc` npmmirror。别改回 `python:3.12-slim` 裸名
- `Dockerfile` 单阶段（需要 `frontend/dist` 在构建上下文，dist 不入库 → 本地先 `npm.cmd run build` 或用 `Dockerfile.full`）；compose 默认 `Dockerfile.full`
- compose 端口 `${APP_PORT:-8000}`；**Windows 本机部署**在 `E:\server\aistudy`，用 `deploy.ps1`（同步代码 + 自动探测可用端口写 `.env` + 重建），别手写端口（WINNAT 排除区间会变）
- 数据外置：`DATA_HOST_DIR` 挂载，用户数据（db/images）不在代码目录

## 协作约定

- **git 只本地 commit，不推 GitHub**（用户明确要求 v6 起不自动更新；推送需用户明说）
- 一次性辅助脚本命名为 `xxx.py` 放根目录，**用完即删**（曾误提交进仓库）
- 改 `models.py` 后必跑 `smoke_test.py` 验证新旧库两条路径；`frontend/dist` 与 `data/` 不入库
- M3 组件库 `@language-lit/material3-expressive` 的 `styles.css` 必须在 `main.tsx` 显式 import（曾漏导致全站无样式）；`npm run test:render` 是防这类回归的冒烟
