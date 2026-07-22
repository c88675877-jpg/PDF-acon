"""Background PDF processing jobs for RQ workers."""

from datetime import datetime
from pathlib import Path
import os

from rq import get_current_job

from analyzer import analyze_pdf_structure, analyze_pdf_vision
from backend_config import settings
from pdf_toc import (
    add_toc_to_pdf,
    estimate_is_scanned,
    extract_text_by_page,
    get_pdf_info,
    verify_toc,
)


settings.ensure_dirs()


def _log(job_id: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{job_id}] {message}", flush=True)


def _job_id() -> str:
    job = get_current_job()
    return job.id if job else "manual"


def _set_progress(step: str, progress: int, error: str | None = None) -> None:
    job = get_current_job()
    if job is None:
        return
    job.meta["step"] = step
    job.meta["progress"] = max(0, min(100, progress))
    if error:
        job.meta["error"] = error
    job.save_meta()


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


def _api_key() -> str:
    key = os.environ.get("MIMO_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("服务器还没有配置 MIMO_API_KEY 环境变量。")
    return key


def process_pdf_job(input_path: str, original_name: str, max_pages: int) -> dict:
    job_id = _job_id()
    input_file = Path(input_path)
    output_path = settings.output_dir / f"{job_id}_{Path(original_name).stem}_with_toc.pdf"

    try:
        if not input_file.is_file():
            raise FileNotFoundError("上传文件不存在或已被清理。")

        _log(job_id, "后台任务开始")
        _set_progress("读取 PDF 基本信息", 15)
        info = get_pdf_info(str(input_file))

        if info["is_encrypted"]:
            raise ValueError("这个 PDF 已加密，请先解密后再上传。")
        if info["has_toc"]:
            existing = verify_toc(str(input_file))
            raise ValueError(f"这个 PDF 已经有 {len(existing)} 个书签，无需重复生成。")

        total_pages = info["page_count"]
        analyzed_pages = max(settings.min_pages, min(total_pages, max_pages, settings.max_pages))

        _log(job_id, f"提取文本：前 {analyzed_pages} 页 / 共 {total_pages} 页")
        _set_progress(f"提取文本：前 {analyzed_pages} 页 / 共 {total_pages} 页", 25)
        pages = extract_text_by_page(str(input_file), max_pages=analyzed_pages)

        if estimate_is_scanned(pages):
            vision_pages = min(analyzed_pages, settings.max_vision_pages)
            _log(job_id, f"扫描件视觉分析：前 {vision_pages} 页")
            _set_progress(f"扫描件视觉分析：前 {vision_pages} 页", 45)
            result = analyze_pdf_vision(str(input_file), _api_key(), max_pages=vision_pages)
        else:
            total_chars = sum(page["char_count"] for page in pages)
            _log(job_id, f"文字型 PDF，提取到 {total_chars} 个字符")
            if total_chars < 100:
                raise ValueError("PDF 中可提取文本太少，可能是扫描件或图片型 PDF。")
            _set_progress("调用文本 AI 分析目录", 45)
            result = analyze_pdf_structure(pages, _api_key())

        toc = result.get("toc", [])
        doc_title = result.get("title", "未命名文档")
        _log(job_id, f"AI 分析完成，识别到 {len(toc)} 个目录项")
        if not toc:
            raise ValueError("AI 没有识别出清晰的目录结构，请换一本章节结构更明确的 PDF 再试。")

        _set_progress("写入 PDF 书签", 80)
        add_toc_to_pdf(str(input_file), toc, str(output_path))
        verified = verify_toc(str(output_path))
        _log(job_id, f"书签写入完成，验证到 {len(verified)} 个书签")

        _set_progress("处理完成", 100)
        return {
            "output_path": str(output_path),
            "download_name": output_path.name,
            "report": _build_report(original_name, doc_title, total_pages, analyzed_pages, verified),
            "toc_count": len(verified),
        }
    except Exception as exc:
        _set_progress("处理失败", 100, str(exc))
        _log(job_id, f"处理失败：{exc}")
        raise
