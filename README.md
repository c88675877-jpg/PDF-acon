# 📚 PDF 智能目录生成器

上传 PDF → AI 分析结构 → 自动生成可点击书签目录

利用 **DeepSeek AI** 智能识别文档章节结构，为 PDF 添加书签（outlines），阅读时可以直接点击跳转。

## ✨ 功能

- 🧠 **AI 分析**：调用 DeepSeek API 理解文档结构，自动提取章节标题
- 📑 **可点击目录**：生成 PDF 标准书签（outlines），阅读器中可直接跳转
- 📱 **手机适配**：响应式设计，手机浏览器也能方便使用
- 🔒 **隐私可控**：自行提供 API Key，数据不经过第三方服务
- 🆓 **零成本部署**：可免费部署到 Hugging Face Spaces

## 🚀 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python app.py

# 3. 打开浏览器访问
# http://localhost:7860
```

### 获取 DeepSeek API Key

1. 访问 [DeepSeek 平台](https://platform.deepseek.com/)
2. 注册账号 → 进入 API Keys 页面
3. 创建新的 API Key（以 `sk-` 开头）

### 部署到 Hugging Face Spaces（免费）

1. Fork 或上传本项目到 GitHub
2. 访问 [Hugging Face Spaces](https://huggingface.co/new-space)
3. 创建新 Space：
   - Space name: `pdf-toc-generator`
   - License: `MIT`
   - SDK: **Gradio**
   - Space hardware: **CPU free**
4. 连接 GitHub 仓库，或直接上传文件
5. 部署完成后即可使用

## 🏗️ 项目结构

```
├── app.py           # 主程序 - Gradio Web 界面
├── pdf_toc.py       # PDF 处理核心（文本提取、书签读写）
├── analyzer.py      # DeepSeek API 交互与提示词
├── requirements.txt # 依赖清单
├── README.md        # 本文件
└── LICENSE
```

## 📖 使用流程

```
1. 上传 PDF 文件
2. 输入 DeepSeek API Key
3. 设置分析页数（默认前 50 页）
4. 点击"开始处理"
5. 预览提取的目录结构
6. 下载带书签的 PDF
```

## ⚙️ 技术实现

- **前端界面**：Gradio（响应式，自动适配移动端）
- **PDF 处理**：PyMuPDF（fitz）
- **AI 分析**：DeepSeek API（deepseek-chat 模型）
- **书签格式**：PDF 标准 Outlines（兼容所有主流阅读器）

### 工作原理

1. PyMuPDF 逐页提取 PDF 文本（保留页码）
2. 将文本按页分段，发送给 DeepSeek API
3. DeepSeek 分析文档结构，返回 JSON 格式的目录
4. PyMuPDF 将目录写入 PDF 书签（`set_toc()`）
5. 输出带可点击目录的 PDF 文件

## 💡 提示

- **参数设置**：大多数 PDF 的章节集中在前 30-50 页，可适当调整
- **扫描件**：本工具不支持纯扫描件（图片型 PDF），请先 OCR 处理
- **加密文件**：不支持加密 PDF，请先解密
- **API 费用**：DeepSeek API 极其便宜（约 ¥0.01-0.03/本）

## 📝 许可证

MIT License
