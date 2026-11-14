# 智学错题本 · AI 学习助手

面向**初一至高三学生与家长**的移动端 Web 应用：拍照解析错题、弱点知识图谱、AI 学习档案、
档案库（课本/笔记/作业数字化）、智能对话——AI 能通过技能体系读写你的全部学习数据，
帮你把零散的学习过程沉淀成可检索、可复习的"第二大脑"。

📱 手机浏览器直接访问 ｜ 🐳 Docker 一键部署（飞牛/绿联 NAS、本机） ｜ 🔌 任意 OpenAI 兼容 API

---

## 功能总览

### 📝 错题
- **拍照/相册/手动录入**：单题、整页多题；上传前**裁切**（框选 + 旋转 + 透视拉正 + 放大镜精修）
- **整页选题流程**：AI 先识别页面题目清单（不作答）→ 勾选做错的题 + 填大致错因 → 按题深度分析
- **自动识别学科**；结构化输出：题干 · 知识点（大方向+二级） · 错因 · 分步解法（LaTeX 公式） · 举一反三 · 答题方法
- **错题本**：筛选/搜索/复习标记；错题照片**自动归档进档案库**

### 🧠 知识图谱
- 统一节点树：学科 → 大方向知识点 → 二级子方向（如「因式分解 → 十字相乘法」）
- **知识点 / 弱点**双类型，掌握度 + 置信度（疑似→已确认，多题印证才确认，判定克制）
- 交互式图谱：拖动布局持久化、点击节点编辑 / 删除 / **AI 结合错题重新总结**、筛选（全部/知识点/弱点）
- 升年级后旧内容归档（保留可查），薄弱点可选择带入继续攻克

### 🗂 档案库（学习资料数字化）
- **书本区**：拍照课本/笔记，按页码排序，电子书式翻页；文字自动提取（AI 视觉 OCR）
- **板块区**：大板块→分板块自由组织（预设：题目版/答案版/解析版/知识点版/订正版）
- **图片库 / 文字 / 附件库**：作业、试卷、老师答案解析（txt/md/pdf/docx 提取文字供 AI 阅读）
- **搜索**：基础关键词直达 + **AI 高级搜索**（全局查找"以前是否出现过"，筛学科/来源）
- **书签**：任意图片/错题/书页一键收藏，统一查看
- 所有资料支持**下载到本地**；错题页可**引用档案内容**向 AI 提问

### 💬 AI 对话（提问板块）
- 流式对话、Markdown + LaTeX 公式、**## 板块化输出**（AI 自由组织内容结构）
- **技能按钮**：整理弱点 / 按错题重评 / 总结成知识点 / 生成刷题目标 / 总结答题方法
- AI 通过 **31 个 Skill** 按需读取图谱/错题/档案/课本，也能写入（增删改全部留痕可撤销）
- **@引用**历史错题/档案随消息带给 AI；**对话摘要**（独立 Agent，结果不进消息流）
- 顶栏会话内**切换模型**；气泡复制/重新生成；生成完成底部**小红点**提醒
- **全局 AI 浮球**：任何页面唤起 AI，自动携带当前页面上下文

### 🤖 AI 能力（Skill 体系）
AI 读写数据的唯一通道是 Skill（JSON 协议，兼容任意 OpenAI 兼容接口）：

| 读技能 | 写技能（全部记变更日志、可撤销） |
|---|---|
| 图谱 / 错题 / 档案 / 课本页 / 附件 / 档案结构 / 进度 / 目标 / 方法 / 变更记录 / 对话历史 / 对话摘要 | 节点增改删 / 整理精简弱点 / 按错题重评 / 更新档案 / 刷题目标 / 方法卡 / 板块管理 / 资料移动删除 / 生成复习资料 / 生成对话摘要 |

每次修改生成**变更卡**（改了什么 + 为什么 + 一键撤销），「我的 → 变更」完整记录。

### 📊 学习成长
- **学习档案**（AI 第二大脑）：弱点画像自动增量更新
- **进度看板**：掌握度统计、学情分析；**学习报告 / 学年总结**生成
- **刷题目标**：按弱点规划"专攻哪类题"（非题海战术）
- **答题方法库**：文科具体方法 + 通用方法自动积累
- **夜间整理**（时间自定义）：OCR → 归档 → 图谱 → 进度 → 当晚简报
- **升年级向导**：AI 学年总结 → 旧内容归档 → 新年级学科调整

### 👥 账号与数据
- 学生/家长自由注册（局域网部署），管理员可停用用户
- **多供应商**：小米 MiMo / DeepSeek 等共存，模型可标"支持视觉"（拍照任务自动路由）
- **导出/导入** ZIP 备份（个人 + 整机，覆盖式恢复，向下兼容），换服务器无忧

---

## 快速部署

### Docker（NAS / 服务器）

```bash
docker compose up -d --build
# 访问 http://<IP>:8000，初始化管理员 → 设置 → 供应商，填 Base URL / API Key / 模型
```

- 镜像默认走国内加速源构建（`docker.1ms.run`、清华 PyPI、npmmirror），飞牛/绿联 NAS 实测可用
- 数据持久化在 `./data`（SQLite + 图片），备份该目录即可

### 本机测试（Windows）

```bash
# 用 deploy/deploy-local.ps1：同步代码 + 自动选可用端口 + 重建（推荐）
powershell -ExecutionPolicy Bypass -File E:\server\aistudy\deploy.ps1
# 或手动：
cd E:\server\aistudy && docker compose up -d --build
```

> ⚠️ Windows 的 WINNAT 动态排除端口段（如 8000/5000 常被占用），端口由 `deploy.ps1`
> 自动探测写入 `.env`（APP_PORT=…）；手动部署时若报 `ports are not available`，
> 换 `.env` 里的端口再 `docker compose up -d` 即可。

### 本地开发

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 前端（另开终端）
cd frontend && npm install && npm run dev   # http://localhost:5173
```

---

## AI API 配置

支持所有 OpenAI 兼容接口（DeepSeek / 小米 MiMo / Kimi / 通义千问 / 智谱 / GLM / OpenRouter …）：

| 配置项 | 示例 |
|---|---|
| Base URL | `https://api.deepseek.com/v1` |
| API Key | `sk-...` |
| 模型 | `deepseek-chat` / `mimo-a`（可加多个，会话内切换） |
| 支持视觉 | 拍照识题/OCR 需要视觉模型（GLM-4V、Qwen-VL、MiMo-VL 等），勾选后自动路由 |

---

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 · TypeScript · Vite · React Flow（图谱）· KaTeX（公式，离线字体）· **Material You 3 Expressive**（@language-lit 组件库 + 官方 shape/spring token） |
| 后端 | FastAPI · SQLAlchemy · SQLite · SSE 流式 |
| AI | OpenAI 兼容协议 · 流式 + 视觉多模态 · JSON Skill 协议（不依赖 function-calling） |
| 部署 | 单镜像 Docker（多阶段构建）· compose · NAS/本机 |

## 项目结构

```
backend/app/
├── main.py            # FastAPI 入口 + 夜间整理调度
├── prompts.py         # 分学科/年级/角色提示词 + Skill 协议
├── services/          # ai_client · skills(31技能) · skill_loop · knowledge · ocr · nightly · grade · …
└── api/               # auth · providers · wrong_questions · chat · knowledge · library · search · changes · data · settings
frontend/src/
├── ui.tsx             # 组件库适配层（Button/Sheet/Dialog/Tabs…）
├── theme.css          # M3 Expressive 设计系统 + 自定义组件
└── pages/             # Home · Mindmap · Upload · WrongList/Detail · ChatList/Room · Library · BookDetail · Search · Mine · Settings
docs/                  # REQUIREMENTS.md（需求核对清单）
```

## 开发测试

```bash
cd backend
python smoke_test.py        # 接口冒烟（40）
python mock_ai_test.py      # AI 管线/技能/搜索（63）
python e2e_library.py       # 档案库（17）
python e2e_v3.py / e2e_v4.py / test_skill_extract.py
cd ../frontend && npm run test:render
```
