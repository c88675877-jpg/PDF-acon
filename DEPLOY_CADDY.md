# Vue + Caddy 部署说明

这个项目现在分成两部分：

- `frontend/`：Vue 前端页面，打包后生成 `frontend/dist`
- `server.py`：Python 后端 API，负责处理 PDF

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

## 服务器运行后端

在服务器项目目录中安装 Python 依赖：

```bash
pip install -r requirements.txt
```

设置接口密钥并启动后端：

```bash
export MIMO_API_KEY="你的 API Key"
python server.py
```

建议正式部署时用 `systemd` 让 `server.py` 常驻运行。

## Caddy 配置

没有域名时可以先用 IP：

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

有域名后改成：

```caddyfile
example.com {
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
