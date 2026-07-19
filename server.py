#!/usr/bin/env python3
"""HTTP API for the Vue version of the PDF TOC generator."""

import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from analyzer import analyze_pdf_structure, analyze_pdf_vision
from pdf_toc import (
    add_toc_to_pdf,
    estimate_is_scanned,
    extract_text_by_page,
    get_pdf_info,
    verify_toc,
)


BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = Path(os.environ.get("PDF_TOC_WORK_DIR", tempfile.gettempdir())) / "pdf_toc_api"
UPLOAD_DIR = WORK_DIR / "uploads"
OUTPUT_DIR = WORK_DIR / "outputs"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "100"))
DEFAULT_MAX_PAGES = 50

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _safe_filename(name: str) -> str:
    base = Path(name).stem or "document"
    ext = Path(name).suffix.lower() or ".pdf"
    safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base).strip()
    return f"{safe_base or 'document'}{ext}"


def _build_report(input_name: str, doc_title: str, total_pages: int, analyzed_pages: int, toc: list) -> str:
    lines = [
        f"处理成功：已添加 {len(toc)} 个 PDF 书签。",
        f"文件：{input_name}",
        f"文档标题：{doc_title}",
        f"分析页数：前 {analyzed_pages} 页 / 共 {total_pages} 页",
        "",
        "目录预览：",
    ]

    for level, title, page in toc:
        indent = "  " * max(level - 1, 0)
        lines.append(f"{indent}- {title}，第 {page} 页")

    return "\n".join(lines)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/process")
def process_pdf():
    api_key = os.environ.get("MIMO_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return _json_error("服务器还没有配置 MIMO_API_KEY 环境变量。", 500)

    uploaded = request.files.get("pdf")
    if uploaded is None or uploaded.filename == "":
        return _json_error("请先上传一个 PDF 文件。")

    if not uploaded.filename.lower().endswith(".pdf"):
        return _json_error("只能上传 PDF 文件。")

    try:
        max_pages = int(request.form.get("max_pages", DEFAULT_MAX_PAGES))
    except ValueError:
        max_pages = DEFAULT_MAX_PAGES
    max_pages = max(5, min(max_pages, 100))

    job_id = uuid.uuid4().hex
    original_name = _safe_filename(uploaded.filename)
    input_path = UPLOAD_DIR / f"{job_id}_{original_name}"
    output_path = OUTPUT_DIR / f"{job_id}_{Path(original_name).stem}_with_toc.pdf"
    uploaded.save(input_path)

    try:
        info = get_pdf_info(str(input_path))
        if info["is_encrypted"]:
            return _json_error("这个 PDF 已加密，请先解密后再上传。")

        if info["has_toc"]:
            existing = verify_toc(str(input_path))
            return _json_error(f"这个 PDF 已经有 {len(existing)} 个书签，无需重复生成。")

        total_pages = info["page_count"]
        analyzed_pages = min(total_pages, max_pages)
        pages = extract_text_by_page(str(input_path), max_pages=analyzed_pages)

        if estimate_is_scanned(pages):
            result = analyze_pdf_vision(str(input_path), api_key, max_pages=min(analyzed_pages, 15))
        else:
            total_chars = sum(page["char_count"] for page in pages)
            if total_chars < 100:
                return _json_error("PDF 中可提取文本太少，可能是扫描件或图片型 PDF。")
            result = analyze_pdf_structure(pages, api_key)

        toc = result.get("toc", [])
        doc_title = result.get("title", "未命名文档")
        if not toc:
            return _json_error("AI 没有识别出清晰的目录结构，请换一本章节结构更明确的 PDF 再试。")

        add_toc_to_pdf(str(input_path), toc, str(output_path))
        verified = verify_toc(str(output_path))
        report = _build_report(original_name, doc_title, total_pages, analyzed_pages, verified)

        return jsonify({
            "download_id": job_id,
            "download_name": output_path.name,
            "report": report,
            "toc_count": len(verified),
        })
    except Exception as exc:
        return _json_error(f"处理失败：{exc}", 500)


@app.get("/api/download/<download_id>")
def download(download_id: str):
    if not download_id or any(c not in "0123456789abcdef" for c in download_id):
        return _json_error("下载链接无效。", 404)

    matches = list(OUTPUT_DIR.glob(f"{download_id}_*.pdf"))
    if not matches:
        return _json_error("文件不存在或已过期。", 404)

    return send_file(matches[0], as_attachment=True, download_name=matches[0].name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port)
