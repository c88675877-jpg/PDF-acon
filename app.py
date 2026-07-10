#!/usr/bin/env python3
"""
PDF 智能目录生成工具 - Gradio Web App
======================================
利用 DeepSeek AI 分析 PDF 文档结构，自动生成可点击的书签目录。
适用部署环境：Hugging Face Spaces / 本地服务器

运行方式:
    python app.py          # 本地运行
    gradio app.py          # 或使用 gradio CLI
"""

import os
import shutil
import tempfile
import gradio as gr

from pdf_toc import (
    extract_text_by_page,
    add_toc_to_pdf,
    verify_toc,
    get_pdf_info,
    estimate_is_scanned,
)
from analyzer import analyze_pdf_structure, analyze_pdf_vision

# ---------- 常量 ----------

DEFAULT_MAX_PAGES = 50
CLEANUP_INTERVAL_SECONDS = 300  # 每5分钟清理一次临时文件
API_KEY = "sk-cz1g01ope3vfsfmzjaejofyyqa3lq4m9elam7w97o9d47t6j"  # MiMo API Key

# ---------- 临时文件管理 ----------

_temp_dir = tempfile.mkdtemp(prefix="pdf_toc_")


def _get_file_path(file_obj) -> str | None:
    """
    兼容 Gradio 5.x 和 6.x 的文件路径提取。
    返回的路径保证文件存在；不存在则返回 None。
    """
    if file_obj is None:
        return None

    raw: str | None = None

    # NamedString / 普通字符串（Gradio 5.x / 6.x 的默认行为）
    if isinstance(file_obj, str):
        raw = file_obj.strip()
    # FileData 对象（Gradio 6.x 部分场景）
    elif hasattr(file_obj, "path"):
        raw = file_obj.path
    # 旧版本 Gradio 的 .name（< 4.0）
    elif hasattr(file_obj, "name"):
        raw = file_obj.name

    if not raw:
        return None

    # 校验路径是否存在；若不存在，尝试用 orig_name 在同目录下查找
    if os.path.isfile(raw):
        return raw

    # 如果有 orig_name，尝试跟 _temp_dir 组合
    orig = getattr(file_obj, "orig_name", None)
    if orig:
        alt = os.path.join(_temp_dir, orig)
        if os.path.isfile(alt):
            return alt

    return None  # 找不到有效文件


def _copy_to_stable(src_path: str) -> str:
    """
    将上传的临时文件复制到应用自己的临时目录，
    避免 Gradio 在函数执行期间清理临时文件。
    如果 src_path 已在我们自己的临时目录中，则跳过复制。
    """
    if src_path.startswith(_temp_dir):
        return src_path  # 已经在稳定目录中
    basename = os.path.basename(src_path)
    dst = os.path.join(_temp_dir, f"upload_{basename}")
    # 避免覆盖已有文件
    counter = 1
    while os.path.isfile(dst):
        name, ext = os.path.splitext(basename)
        dst = os.path.join(_temp_dir, f"upload_{name}_{counter}{ext}")
        counter += 1
    shutil.copy2(src_path, dst)
    return dst


def _safe_path(original_name: str) -> str:
    """生成安全的输出文件路径"""
    base = os.path.splitext(os.path.basename(original_name))[0]
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
    return os.path.join(_temp_dir, f"{safe_name}_带目录.pdf")


# ---------- 核心处理函数 ----------

def process_pdf(
    pdf_file,
    max_pages: int,
    progress: gr.Progress = gr.Progress(),
):
    """
    处理 PDF 的主流程：
    1. 验证输入
    2. 提取文本
    3. DeepSeek 分析结构
    4. 写入书签
    5. 返回结果
    """
    # --- 验证输入 ---
    if pdf_file is None:
        return None, "❌ 请先上传一个 PDF 文件"

    # 使用代码中内置的 API Key
    api_key = API_KEY

    input_path = _get_file_path(pdf_file)
    if not input_path:
        return None, "❌ 无法读取上传的文件，请重新选择文件"

    # 复制到稳定的临时目录，防止 Gradio 在函数执行期间清理临时文件
    input_path = _copy_to_stable(input_path)

    try:
        # --- 获取 PDF 信息 ---
        progress(0, desc="📖 读取 PDF 信息...")
        info = get_pdf_info(input_path)

        if info["is_encrypted"]:
            return None, "❌ 该 PDF 文件已加密，请先解密后再处理"

        page_count_display = info["page_count"]
        actual_pages = min(page_count_display, max_pages)

        if info["has_toc"]:
            existing = verify_toc(input_path)
            return None, (
                f"📌 该 PDF 已有 {len(existing)} 个书签，无需再次生成。\n\n"
                f"如需重新生成，请先移除原有书签。"
            )

        # --- 提取文本 ---
        progress(0.1, desc=f"📝 提取前 {actual_pages} 页文本...")
        pages = extract_text_by_page(input_path, max_pages=actual_pages)

        # 检查是否为扫描件
        is_scanned = estimate_is_scanned(pages)

        if is_scanned:
            progress(0.2, desc="🖼️ 检测为扫描件，使用 MiMo 视觉 AI 分析...")
            result = analyze_pdf_vision(
                input_path,
                api_key,
                max_pages=actual_pages,
            )
        else:
            total_chars = sum(p["char_count"] for p in pages)
            if total_chars < 100:
                return None, (
                    "❌ PDF 中提取的文本太少（不足100字符），无法分析文档结构。\n\n"
                    "💡 这可能是扫描件或加密文档。"
                )

            # --- MiMo API 分析 ---
            progress(0.3, desc="🤖 正在调用 MiMo API 分析文档结构...")
            result = analyze_pdf_structure(pages, api_key)

        toc = result.get("toc", [])
        doc_title = result.get("title", "未命名文档")

        if not toc:
            return None, (
                "⚠️ DeepSeek 未能识别出文档的章节结构。\n\n"
                "可能原因：\n"
                "1. 文档没有清晰的章节标题格式\n"
                "2. 文档内容较少，不需要目录\n"
                "3. API 返回格式异常\n\n"
                f"文档标题推测：{doc_title}\n"
                f"分析页数：{actual_pages} 页"
            )

        # --- 写入书签 ---
        progress(0.7, desc="📑 正在写入 PDF 书签...")
        output_path = _safe_path(input_path)
        add_toc_to_pdf(input_path, toc, output_path)

        # --- 验证 ---
        progress(0.9, desc="✅ 验证书签...")
        verified = verify_toc(output_path)

        # --- 构建预览文本 ---
        lines = []
        lines.append(f"✅ 成功添加 {len(verified)} 个书签！\n")
        lines.append(f"📄 文档：{os.path.basename(input_path)}")
        lines.append(f"🏷️  文档标题：{doc_title}")
        lines.append(f"📊 分析页数：前 {actual_pages} 页 / 共 {page_count_display} 页\n")
        lines.append("📋 目录结构预览：")
        lines.append("─" * 40)

        for item in verified:
            level, title, page = item
            indent = "  " * (level - 1)
            prefix = "├─" if level == 1 else "│ "
            lines.append(f"{indent}{prefix} {title}  → 第{page}页")

        if result.get("raw_count", 0) > len(verified):
            lines.append(
                f"\n💡 提示：API 返回了 {result['raw_count']} 个条目，"
                f"其中 {len(verified)} 个格式有效"
            )

        return output_path, "\n".join(lines)

    except Exception as e:
        return None, (
            f"❌ 处理失败：{str(e)}\n\n"
            f"📎 文件：{os.path.basename(input_path)}"
        )


# ---------- Gradio 界面 ----------

CSS = """
/* 移动端适配 */
@media (max-width: 640px) {
    .main-container {
        flex-direction: column !important;
    }
    .input-panel, .output-panel {
        max-width: 100% !important;
        min-width: 100% !important;
    }
}
.container { max-width: 900px; margin: 0 auto; }
footer { display: none !important; }
.app-title { text-align: center; margin-bottom: 0.5rem; }
.app-subtitle { text-align: center; color: #666; margin-top: 0; margin-bottom: 1.5rem; }
"""

with gr.Blocks(
    title="PDF 智能目录生成器",
) as demo:

    # ---- 头部 ----
    gr.Markdown(
        """
        # 📚 PDF 智能目录生成器

        上传 PDF → AI 分析结构 → 生成可点击书签目录

        使用 **DeepSeek AI** 智能识别文档章节，为你的 PDF 添加方便的导航目录。
        """,
        elem_classes="app-title",
    )

    with gr.Row(elem_classes="main-container"):
        # ---- 左侧：输入面板 ----
        with gr.Column(scale=1, elem_classes="input-panel"):
            gr.Markdown("### 📤 输入设置")

            pdf_input = gr.File(
                label="选择 PDF 文件",
                file_types=[".pdf"],
                file_count="single",
                scale=1,
            )

            max_pages = gr.Slider(
                label="分析前 N 页",
                minimum=5,
                maximum=100,
                value=DEFAULT_MAX_PAGES,
                step=5,
                info="大多数 PDF 的目录和章节标题集中在前 30-50 页",
            )

            process_btn = gr.Button(
                "🚀 开始处理",
                variant="primary",
                size="lg",
            )

            with gr.Accordion("💡 使用说明", open=False):
                gr.Markdown(
                    """
                    ### 使用方法
                    1. **上传 PDF**：选择你要处理的 PDF 文件（最大 100MB）
                    2. **点击处理**：等待 AI 分析完成（约 30 秒 - 2 分钟）
                    3. **下载结果**：获取带可点击书签的 PDF

                    ### 费用参考
                    DeepSeek API 极其便宜：处理一本 300 页的书约 ¥0.01-0.03

                    ### 隐私说明
                    你的 PDF 文本会发送到 DeepSeek API 进行分析，建议不要上传涉密文件。
                    """
                )

        # ---- 右侧：输出面板 ----
        with gr.Column(scale=1, elem_classes="output-panel"):
            gr.Markdown("### 📥 输出结果")

            pdf_output = gr.File(
                label="下载带目录的 PDF",
                visible=True,
                scale=1,
            )

            result_preview = gr.Textbox(
                label="处理报告",
                lines=18,
                max_lines=35,
                placeholder="处理完成后会在这里显示结果预览...",
            )

    # ---- 事件绑定 ----
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, max_pages],
        outputs=[pdf_output, result_preview],
        concurrency_limit=1,  # 免费服务器上一次只处理一个请求
    )

    # 上传新文件时清空旧结果
    pdf_input.change(
        fn=lambda: (None, ""),
        outputs=[pdf_output, result_preview],
    )


# ---------- 入口 ----------

if __name__ == "__main__":
    print(f"🚀 启动 PDF 智能目录生成器...")
    print(f"📁 临时文件目录: {_temp_dir}")
    print(f"💡 按 Ctrl+C 停止服务")

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        theme=gr.themes.Soft(
            primary_hue="blue",
            neutral_hue="slate",
            font=gr.themes.GoogleFont("Noto Sans SC"),
        ),
        css=CSS,
    )
