# PDF 智能目录生成器

上传 PDF，后台调用 AI 分析章节结构，并生成带可点击书签目录的 PDF。

这个版本已经改造成正式的前后端分离结构，适合部署到自己的 Linux 服务器：

- Vue + Vite：浏览器前端，支持上传进度和任务进度显示
- Flask + Gunicorn：后端 API，负责上传、创建任务、查询状态、下载结果
- Redis + RQ：后台任务队列，避免大 PDF 或扫描件让网页请求卡死
- PyMuPDF：提取文本、渲染扫描件页面、写入 PDF 书签
- Caddy：对外提供网站，并把 `/api/*` 转发给后端

## 功能

- PDF 上传后创建后台任务，页面自动轮询处理进度
- 支持文字型 PDF 的文本目录分析
- 支持扫描件 PDF 的前几页视觉分析
- 自动写入 PDF 标准书签 outlines
- 大文件上传有进度反馈，不再依赖一个长时间同步请求
- 后端统一配置上传大小、分析页数、任务超时和文件保留时间

## 项目结构

```text
.
├── frontend/            # Vue 前端
│   ├── src/
│   └── package.json
├── server.py            # Flask API：上传、任务状态、下载
├── tasks.py             # RQ 后台任务：真正处理 PDF
├── worker.py            # RQ worker 启动入口
├── backend_config.py    # 后端配置
├── cleanup_jobs.py      # 清理过期上传和输出文件
├── analyzer.py          # AI 分析逻辑
├── pdf_toc.py           # PDF 文本提取和书签写入
├── app.py               # 旧 Gradio 入口，保留用于参考/本地旧版运行
├── requirements.txt
└── DEPLOY_CADDY.md      # 详细 Caddy + systemd 部署说明
```

## 本地开发

### 后端

本地需要先启动 Redis。

```bash
python -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
export MIMO_API_KEY="你的 API Key"
gunicorn -w 2 -b 127.0.0.1:7860 server:app
```

另开一个终端启动 worker：

```bash
source ./venv/bin/activate
export MIMO_API_KEY="你的 API Key"
python worker.py
```

健康检查：

```bash
curl http://127.0.0.1:7860/api/health
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

生产构建：

```bash
npm run build
```

构建产物在：

```text
frontend/dist
```

## 服务器 clone

在服务器上安装 Git 后执行：

```bash
cd /home/ubuntu
git clone https://github.com/c88675877-jpg/PDF-acon.git pdf-toc-api
cd pdf-toc-api
```

如果服务器提示没有安装 Git：

```bash
sudo apt update
sudo apt install -y git
```

后续服务器部署请按 [DEPLOY_CADDY.md](./DEPLOY_CADDY.md) 操作。

核心流程是：

```text
1. 安装 Redis、Python venv、Node.js/Caddy
2. pip install -r requirements.txt
3. cd frontend && npm install && npm run build
4. 把 frontend/dist 内容复制到 /var/www/vue
5. 用 systemd 启动 API 和 worker
6. Caddy 转发 /api/* 到 127.0.0.1:7860
```

## 重要环境变量

```text
MIMO_API_KEY          必填，AI 接口密钥
REDIS_URL            默认 redis://127.0.0.1:6379/0
PDF_TOC_WORK_DIR     默认系统临时目录，用于保存上传和输出文件
MAX_UPLOAD_MB        默认 100
DEFAULT_ANALYZE_PAGES 默认 50
MAX_ANALYZE_PAGES    默认 100
MAX_VISION_PAGES     默认 5
JOB_TIMEOUT_SECONDS  默认 1800
JOB_TTL_SECONDS      默认 604800
```

## API 简介

```text
GET  /api/health
POST /api/jobs
GET  /api/jobs/<job_id>
GET  /api/jobs/<job_id>/download
```

旧接口 `/api/process` 已废弃。

## 注意

- 不要把 `.env`、API Key、上传文件、输出文件提交到 Git。
- 大扫描件建议调低分析页数，默认视觉分析只看前 5 页。
- 如果 `/api/health` 返回 Redis 不可用，先检查 `redis-server` 是否启动。

## License

MIT
