"""
PDF 目录处理核心模块
====================
使用 PyMuPDF (fitz) 提取 PDF 文本、读写书签（outlines）。
"""

import base64
import fitz
from typing import Optional


def get_pdf_info(pdf_path: str) -> dict:
    """获取 PDF 基本信息"""
    doc = fitz.open(pdf_path)
    info = {
        "page_count": len(doc),
        "file_size": None,  # 由调用方填充
        "metadata": doc.metadata,
        "has_toc": len(doc.get_toc()) > 0,
        "is_encrypted": doc.is_encrypted,
    }
    doc.close()
    return info


def extract_text_by_page(pdf_path: str, max_pages: int = 50) -> list[dict]:
    """
    逐页提取 PDF 文本内容。

    参数:
        pdf_path: PDF 文件路径
        max_pages: 最多提取页数（前 N 页）

    返回:
        [{"page_num": 1, "text": "...", "char_count": 123}, ...]
    """
    doc = fitz.open(pdf_path)
    total_pages = min(len(doc), max_pages)
    pages = []

    for i in range(total_pages):
        page = doc[i]
        text = page.get_text("text").strip()
        # 也尝试用 "blocks" 方式获取更丰富的文本
        if not text:
            blocks = page.get_text("blocks")
            text = "\n".join(
                b[4].strip() for b in blocks if b[6] == 0  # type=0 表示文本块
            )
        pages.append({
            "page_num": i + 1,  # 1-indexed
            "text": text,
            "char_count": len(text),
        })

    doc.close()
    return pages


def add_toc_to_pdf(
    input_path: str,
    toc_data: list[dict],
    output_path: str,
) -> str:
    """
    将目录结构写入 PDF 文件作为可点击书签（outlines）。

    toc_data 格式:
        [
            {"level": 1, "title": "第一章", "page": 3},
            {"level": 2, "title": "1.1 背景", "page": 3},
            ...
        ]

    PyMuPDF 的 set_toc 接受: [[level, title, page], ...]
        level: 1=一级标题, 2=二级, 3=三级 ...
        title: 标题文本
        page: PDF 内部页码（1-indexed）
    """
    doc = fitz.open(input_path)

    # 转换为 PyMuPDF 内部格式
    toc = [
        [item["level"], item["title"], item["page"]]
        for item in toc_data
    ]

    # 写入书签
    doc.set_toc(toc)

    # 保存（garbage=4 做最大程度优化，deflate 压缩）
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def verify_toc(pdf_path: str) -> list:
    """
    验证 PDF 文件中的书签。

    返回: [[level, title, page], ...] 或空列表
    """
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    doc.close()
    return toc


def estimate_is_scanned(pages: list[dict], threshold: float = 0.1) -> bool:
    """
    粗略判断 PDF 是否为扫描件（图片型，没有可提取文本）。
    如果大部分页面文本内容极少，判定为扫描件。
    """
    if not pages:
        return True
    empty_count = sum(1 for p in pages if p["char_count"] < 20)
    return (empty_count / len(pages)) > threshold


# ---------- 扫描件支持：PDF 页面渲染为图片 ----------


def pdf_page_to_base64(pdf_path: str, page_index: int, max_width: int = 500) -> str:
    """将 PDF 单页渲染为 base64 JPEG 图片"""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    zoom = max_width / page.rect.width
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    img_bytes = pix.tobytes("jpeg")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def render_pdf_pages_base64(pdf_path: str, max_pages: int = 50, max_width: int = 500) -> list[dict]:
    """将 PDF 前 N 页逐页渲染为 base64 图片列表"""
    doc = fitz.open(pdf_path)
    total = min(len(doc), max_pages)
    pages = []
    for i in range(total):
        zoom = max_width / doc[i].rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = doc[i].get_pixmap(matrix=matrix)
        img_bytes = pix.tobytes("jpeg")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        pages.append({
            "page_num": i + 1,
            "image_base64": b64,
        })
    doc.close()
    return pages
