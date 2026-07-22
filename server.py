#!/usr/bin/env python3
"""HTTP API for uploading PDFs and tracking background TOC jobs."""

from datetime import datetime
from pathlib import Path
import uuid

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from werkzeug.exceptions import RequestEntityTooLarge

from backend_config import settings


HEX_CHARS = set("0123456789abcdef")


settings.ensure_dirs()
redis_conn = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
queue = Queue(settings.queue_name, connection=redis_conn, default_timeout=settings.job_timeout_seconds)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes
CORS(app)


def _log(scope: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{scope}] {message}", flush=True)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _is_job_id(value: str) -> bool:
    return bool(value) and len(value) == 32 and all(char in HEX_CHARS for char in value)


def _safe_filename(name: str) -> str:
    source = Path(name or "document.pdf")
    ext = source.suffix.lower() if source.suffix.lower() == ".pdf" else ".pdf"
    stem = "".join(char if char.isalnum() or char in " _-" else "_" for char in source.stem).strip()
    return f"{stem or 'document'}{ext}"


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def _parse_max_pages(raw: str | None) -> int:
    try:
        value = int(raw) if raw else settings.default_pages
    except ValueError:
        value = settings.default_pages
    return max(settings.min_pages, min(value, settings.max_pages))


def _safe_output_path(path_value: str) -> Path | None:
    if not path_value:
        return None
    output_root = settings.output_dir.resolve()
    candidate = Path(path_value).resolve()
    if candidate == output_root or output_root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _serialize_job(job: Job) -> dict:
    status = job.get_status(refresh=True)
    meta = job.get_meta(refresh=True) or {}
    payload = {
        "job_id": job.id,
        "status": status,
        "step": meta.get("step", "等待处理"),
        "progress": int(meta.get("progress", 0) or 0),
        "input_name": meta.get("input_name", ""),
    }

    if status == "finished":
        result = job.result or {}
        payload.update({
            "step": "处理完成",
            "progress": 100,
            "report": result.get("report", ""),
            "toc_count": result.get("toc_count", 0),
            "download_name": result.get("download_name", ""),
            "download_url": f"/api/jobs/{job.id}/download",
        })
    elif status == "failed":
        payload.update({
            "step": "处理失败",
            "progress": 100,
            "error": meta.get("error") or "处理失败，请查看 worker 日志。",
        })

    return payload


def _fetch_job(job_id: str) -> Job | None:
    if not _is_job_id(job_id):
        return None
    try:
        return Job.fetch(job_id, connection=redis_conn)
    except (NoSuchJobError, RedisError):
        return None


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    return _json_error(f"PDF 太大了，当前最大允许 {settings.max_upload_mb}MB。", 413)


@app.errorhandler(RedisError)
def handle_redis_error(error):
    _log("redis", f"Redis 错误：{error}")
    return _json_error("任务队列暂时不可用，请稍后再试。", 503)


@app.get("/api/health")
def health():
    try:
        redis_conn.ping()
    except RedisError:
        return jsonify({"ok": False, "redis": False}), 503
    return jsonify({"ok": True, "redis": True})


@app.post("/api/jobs")
def create_job():
    request_id = uuid.uuid4().hex
    _log(request_id, "收到上传请求")
    _log(request_id, f"请求体大小：{_format_size(request.content_length)}")

    redis_conn.ping()

    if request.content_length and request.content_length > settings.max_upload_bytes:
        return _json_error(f"PDF 太大了，当前最大允许 {settings.max_upload_mb}MB。", 413)

    _log(request_id, "开始解析上传表单")
    uploaded = request.files.get("pdf")
    _log(request_id, "上传表单解析完成")

    if uploaded is None or uploaded.filename == "":
        return _json_error("请先上传一个 PDF 文件。")
    if not uploaded.filename.lower().endswith(".pdf"):
        return _json_error("只能上传 PDF 文件。")

    max_pages = _parse_max_pages(request.form.get("max_pages"))
    job_id = uuid.uuid4().hex
    original_name = _safe_filename(uploaded.filename)
    input_path = settings.upload_dir / f"{job_id}_{original_name}"

    _log(job_id, f"保存上传文件：{original_name}")
    uploaded.save(input_path)
    saved_size = input_path.stat().st_size
    _log(job_id, f"上传文件保存完成：{_format_size(saved_size)}")

    if saved_size == 0:
        input_path.unlink(missing_ok=True)
        return _json_error("上传的 PDF 文件为空。")

    job = queue.enqueue(
        "tasks.process_pdf_job",
        str(input_path),
        original_name,
        max_pages,
        job_id=job_id,
        meta={
            "step": "已上传，等待后台处理",
            "progress": 10,
            "input_name": original_name,
            "input_size": saved_size,
        },
        result_ttl=settings.job_ttl_seconds,
        failure_ttl=settings.job_ttl_seconds,
        ttl=settings.job_ttl_seconds,
    )
    _log(job_id, "任务已加入队列")
    return jsonify(_serialize_job(job)), 202


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = _fetch_job(job_id)
    if job is None:
        return _json_error("任务不存在。", 404)
    return jsonify(_serialize_job(job))


@app.get("/api/jobs/<job_id>/download")
def download_job_result(job_id: str):
    job = _fetch_job(job_id)
    if job is None:
        return _json_error("任务不存在。", 404)
    if job.get_status(refresh=True) != "finished":
        return _json_error("任务还没有处理完成。", 409)

    result = job.result or {}
    output_path = _safe_output_path(result.get("output_path", ""))
    if output_path is None:
        return _json_error("文件不存在或已过期。", 404)

    return send_file(output_path, as_attachment=True, download_name=output_path.name)


@app.post("/api/process")
def legacy_process_pdf():
    return _json_error("这个接口已升级，请使用 /api/jobs 创建后台任务。", 410)


if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port)
