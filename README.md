# 智学错题本 · AI 学习助手

面向初一至高三学生的移动端 Web 应用：拍照上传错题 → AI 结构化解析 → 弱点图谱 → 学习进度追踪 → 智能对话。支持 Docker 部署到家庭 NAS，手机浏览器直接访问。

## 功能

| 模块 | 说明 |
|---|---|
| 📸 错题录入 | 拍照 / 相册 / 手动文字 / 整页试卷多题批量识别 |
| 🔍 结构化分析 | 题干识别 · 知识点 · 错因分析 · 分步解法 · 举一反三 · 答题方法 |
| 📝 错题本 | 按学科/知识点筛选、搜索、复习标记，历史错题供后续对话自动调用 |
| 🧠 弱点思维导图 | 交互式节点图（学科→单元→知识点），颜色=掌握度，点击节点进入 AI 深聊 |
| 🔭 学习进度 | 扫描作业识别「正在学什么」（课时不按序也能识别），AI 自动掌握学习进度 |
| 🎯 刷题目标 | AI 按弱点给出专攻题型方向，而非题海战术 |
| 🧭 答题方法库 | 文科（政治/历史/地理等）具体方法 + 通用方法自动积累 |
| 💬 AI 对话 | 多会话流式对话，AI 可通过**技能**读取图谱/错题/档案并修改数据，变更卡可撤销 |
| 🧠 Skill 系统 | 读/写技能（整理弱点、按错题重评、总结入库、更新档案…），技能按钮+AI 自主调用 |
| 🗂 变更可见 | AI 每次修改都有变更卡（改了什么+为什么）+ 全局变更记录，一键撤销 |
| 🔌 多供应商 | 小米 MiMo / DeepSeek 等多供应商共存，对话内自由切换模型 |
| 💾 数据迁移 | 导出/导入 ZIP 备份（个人+整机），覆盖式恢复，换服务器无忧 |
| 🧬 学习档案 | AI 第二大脑：自动维护弱点画像，越用越懂你 |
| 📊 进度看板 | 各科掌握度统计 + AI 学习报告 |
| 👥 多用户 | 学生/家长自由注册（局域网内部署），管理员可停用用户；API Key 可多供应商配置 |

## 快速部署（Docker）

```bash
docker compose up -d --build
```

打开 `http://<NAS-IP>:8000`，首次访问初始化管理员 → 进入「设置 → 全局 AI」填写 API。之后学生/家长可自由注册（登录页 → 注册）。

> 默认 `Dockerfile` 为单阶段构建（前端 `frontend/dist` 已预构建好），只需拉取 `python:3.12-slim` 一个基础镜像。
> 若修改了前端源码，先 `cd frontend && npm run build` 再构建镜像；或改用 `Dockerfile.full`（`docker build -f Dockerfile.full .`）从源码完整构建。

### 飞牛 fnOS 部署 / 拉镜像 401 修复

构建时报 `401 Unauthorized ... docker.fnnas.com` 是因为 fnOS 的默认镜像加速源拒绝了匿名拉取（与本项目无关）。

**本项目已自带修复**：`Dockerfile` 的 `FROM` 默认直接使用可用镜像源 `docker.1ms.run`（已实测可匿名拉取），**绕过 NAS 失效的加速器**，并且 pip 走清华源。换好后在 fnOS Docker 里重新构建即可，无需改动 NAS 设置。

构建参数可切换镜像源（可选）：

```bash
# 改回 Docker Hub 官方源（网络可达时）
docker build --build-arg PYTHON_IMAGE=python:3.12-slim .
# 或换其它加速源
docker build --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim .
```

若你希望从 NAS 系统层面修复加速器（对所有镜像生效），二选一：

**方法 A（图形界面）**：fnOS 的 Docker 应用 →「设置 / 镜像加速（Registry）」→ 移除失效的 `docker.fnnas.com`，添加 `https://docker.1ms.run` 等可用源。

**方法 B（SSH）**：用 `deploy/fnos-daemon.json` 覆盖配置并重启 Docker：

```bash
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak 2>/dev/null
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
    "https://dockerproxy.net"
  ]
}
EOF
sudo systemctl restart docker
```

（可用性实测脚本：`python deploy/check_base_images.py`；1panel 源当前返回 403 已弃用。）

若所有加速源都不可用（少数网络环境），可在任何有 Docker 的机器上 `docker build -t ai-wrong-question:latest .` 后 `docker save ai-wrong-question:latest -o ai-wrong-question.tar.gz`，再在 fnOS Docker 的「镜像 → 导入」加载，无需在 NAS 上构建。

### AI API 配置（OpenAI 兼容）

支持 DeepSeek / Kimi / 通义千问 / 智谱 / OpenRouter 等：

| 配置项 | 示例 |
|---|---|
| Base URL | `https://api.deepseek.com/v1` |
| API Key | `sk-...` |
| 对话模型 | `deepseek-chat` / `kimi-k2-0905-preview` / `qwen-plus` |
| 视觉模型（拍照识别必填） | `glm-4v-plus` / `qwen-vl-max` / `gpt-4o-mini` |

数据保存在 `./data`（SQLite 数据库 + 图片），备份该目录即可。

### 绿联 NAS（UGOS Pro）部署

绿联 Docker 的「JSON 容器配置」即 **Docker Engine API 的容器定义**，已生成在 `deploy/ugreen-container.json`。先把镜像推到 NAS，再导入该配置：

```bash
# 1. 本机构建并导出镜像（NAS 无外网时用；有网可在 NAS 上直接 build）
docker build -t ai-wrong-question:latest .
docker save ai-wrong-question:latest -o ai-wrong-question.tar.gz
```

在绿联 **Docker → 镜像 → 导入** 加载 `ai-wrong-question.tar.gz`，然后 **创建容器 → 导入配置** 粘贴 `deploy/ugreen-container.json`。

⚠️ 只需按你的实际路径改一处：`HostConfig.Binds` 里的宿主机数据目录（`/volume1/docker/ai-wrong-question/data`），换成你 NAS 上想存放数据的文件夹（绿联一般在 `/volume1/...` 或你建的共享文件夹下，先用文件管理器建好 `data` 目录）。

字段说明：

| 字段 | 作用 |
|---|---|
| `Image` | 镜像名，与导入的镜像一致 |
| `ExposedPorts` / `PortBindings` | 容器 8000 映射到 NAS 的 8000（可改 HostPort） |
| `HostConfig.Binds` | 数据卷，**数据库和图片都在这里**，务必持久化 |
| `RestartPolicy` | `unless-stopped` 开机自启/崩溃自动重启 |
| `Env` | `DATA_DIR=/data` 指向容器内数据目录，勿改 |

若你的绿联界面不收 JSON 而收 **Compose YAML** 或 **docker run 命令**，用下面任一等价方式：

<details><summary>docker run 等价命令</summary>

```bash
docker run -d --name ai-wrong-question \
  -p 8000:8000 \
  -v /volume1/docker/ai-wrong-question/data:/data \
  -e DATA_DIR=/data -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  ai-wrong-question:latest
```
</details>

<details><summary>docker-compose.yml（项目根目录已含）</summary>

```yaml
services:
  app:
    image: ai-wrong-question:latest
    container_name: ai-wrong-question
    ports: ["8000:8000"]
    volumes: ["./data:/data"]
    environment: ["DATA_DIR=/data", "TZ=Asia/Shanghai"]
    restart: unless-stopped
```
</details>

部署后手机浏览器访问 `http://<NAS内网IP>:8000`。

### 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev   # http://localhost:5173，自动代理 /api
```

生产构建：`cd frontend && npm run build`，后端会自动托管 `frontend/dist`。

### 开发测试

```bash
cd backend
python smoke_test.py      # 接口冒烟（26 项）
python mock_ai_test.py    # AI 管线端到端（25 项，内置 mock AI）
python mock_ai_server.py  # 独立 mock OpenAI 服务（联调用，默认端口 8901）
```

## 目录结构

```
backend/app/
├── main.py            # FastAPI 入口 + 静态托管
├── prompts.py         # 分学科/分角色提示词体系
├── services/          # AI 客户端 · 错题分析 · 检索 · 档案 · 进度 · 方法 · 报告
└── api/               # auth · settings · wrong-questions · chat(SSE) · knowledge
frontend/src/
├── theme.css          # Material You 3 Expressive 设计系统
└── pages/             # Home · Mindmap · Upload · WrongList · WrongDetail · Chat · Mine · Settings
```

## 技术栈

- 前端：React 18 + Vite + TypeScript + React Flow（思维导图），Material You 3 Expressive 设计语言
- 后端：FastAPI + SQLAlchemy + SQLite
- AI：OpenAI 兼容协议（流式 SSE + 视觉多模态）
- 部署：单容器多阶段构建，适配群晖 / 威联通 NAS
