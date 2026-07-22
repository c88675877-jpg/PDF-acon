# Vue + Caddy + 后台任务部署说明

这个项目现在是正式的前后端分离结构：

- `frontend/`：Vue 前端页面，打包后生成 `frontend/dist`
- `server.py`：API 服务，负责上传文件、创建任务、查询任务、下载结果
- `tasks.py`：后台任务逻辑，负责真正处理 PDF
- `worker.py`：后台 worker，负责从队列里取任务执行
- `backend_config.py`：后端共享配置
- `cleanup_jobs.py`：清理过期上传文件和结果文件
- Redis：任务队列
- Caddy：对外提供网站，并把 `/api/*` 转发给后端

## 本地构建前端

```bash
cd frontend
npm install
npm run build
```

把 `frontend/dist` 里面的内容上传到服务器：

```text
/var/www/vue
```

最终应该看到：

```text
/var/www/vue/index.html
/var/www/vue/assets
```

## 服务器安装基础服务

```bash
sudo apt update
sudo apt install -y redis-server python3-pip python3-venv
sudo systemctl enable --now redis-server
```

检查 Redis：

```bash
redis-cli ping
```

正常返回：

```text
PONG
```

## 上传后端文件

建议后端目录：

```text
/home/ubuntu/pdf-toc-api
```

需要上传这些文件：

```text
server.py
backend_config.py
tasks.py
worker.py
analyzer.py
pdf_toc.py
cleanup_jobs.py
requirements.txt
```

然后安装 Python 依赖：

```bash
cd /home/ubuntu/pdf-toc-api
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

## 手动测试 API 和 worker

开第一个 Termius 窗口，启动 API：

```bash
cd /home/ubuntu/pdf-toc-api
source ./venv/bin/activate
export MIMO_API_KEY="你的 API Key"
gunicorn -w 2 -b 127.0.0.1:7860 server:app
```

开第二个 Termius 窗口，启动 worker：

```bash
cd /home/ubuntu/pdf-toc-api
source ./venv/bin/activate
export MIMO_API_KEY="你的 API Key"
python worker.py
```

检查 API：

```bash
curl -i http://127.0.0.1:7860/api/health
curl -i http://127.0.0.1/api/health
```

都正常后，再访问网站上传 PDF。

## Caddy 配置

没有域名时先用 IP：

```caddyfile
:80 {
    handle /api/* {
        reverse_proxy 127.0.0.1:7860
    }

    handle {
        root * /var/www/vue
        try_files {path} /index.html
        file_server
    }
}
```

检查并重载 Caddy：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## systemd 后台运行

手动测试成功后，再创建后台服务。这样 Termius 关掉以后，网站也能继续工作。

### API 服务

```bash
sudo nano /etc/systemd/system/pdf-toc-api.service
```

内容：

```ini
[Unit]
Description=PDF TOC API
After=network.target redis-server.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/pdf-toc-api
Environment="MIMO_API_KEY=你的 API Key"
Environment="REDIS_URL=redis://127.0.0.1:6379/0"
Environment="PDF_TOC_WORK_DIR=/home/ubuntu/pdf-toc-work"
ExecStart=/home/ubuntu/pdf-toc-api/venv/bin/gunicorn -w 2 -b 127.0.0.1:7860 server:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Worker 服务

```bash
sudo nano /etc/systemd/system/pdf-toc-worker.service
```

内容：

```ini
[Unit]
Description=PDF TOC Worker
After=network.target redis-server.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/pdf-toc-api
Environment="MIMO_API_KEY=你的 API Key"
Environment="REDIS_URL=redis://127.0.0.1:6379/0"
Environment="PDF_TOC_WORK_DIR=/home/ubuntu/pdf-toc-work"
ExecStart=/home/ubuntu/pdf-toc-api/venv/bin/python worker.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pdf-toc-api
sudo systemctl enable --now pdf-toc-worker
```

查看状态：

```bash
sudo systemctl status pdf-toc-api
sudo systemctl status pdf-toc-worker
```

查看日志：

```bash
journalctl -u pdf-toc-api -f
journalctl -u pdf-toc-worker -f
```

## 可选：定期清理旧文件

任务和文件默认保留 7 天。可以每天执行一次：

```bash
cd /home/ubuntu/pdf-toc-api
source ./venv/bin/activate
PDF_TOC_WORK_DIR=/home/ubuntu/pdf-toc-work python cleanup_jobs.py
```
