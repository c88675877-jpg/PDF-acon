"""
DeepSeek API 分析模块
=====================
调用 DeepSeek API 分析 PDF 文本结构，提取目录信息。
"""

import json
import time
from typing import Optional
from openai import OpenAI

# ---------- 提示词 ----------

SYSTEM_PROMPT = """你是一个专业的PDF文档结构分析助手。

任务：分析PDF文本内容，提取完整的目录/大纲结构。

你需要识别文档中的各级标题：
- 一级标题：大章节标题，如"第X章"、"第X部分"、"Introduction"、"Methodology"等
- 二级标题：节标题，如"X.X"格式、带编号的小节
- 三级标题：子节标题，如"X.X.X"格式

判断标题的线索：
1. 独立成行、字数较少（通常不超过30字）
2. 有编号体系（一、二、三 / 1, 2, 3 / 1.1, 1.2 / 第一章, 第二章）
3. 上下文：标题后紧跟正文内容
4. 如果某行看起来像标题但不确定，宁可不提取也不要错提取"""


def build_user_prompt(pages_text: list[dict]) -> str:
    """
    构建用户提示词，将分页文本组装成带页码标记的格式。
    """
    text_blocks = []
    for p in pages_text:
        label = f"--- Page {p['page_num']} ---"
        content = p["text"][:2000]  # 每页最多取 2000 字符
        text_blocks.append(f"{label}\n{content}")

    combined = "\n\n".join(text_blocks)

    return f"""请分析以下PDF每页的文本内容，提取文档的目录结构。

文本内容（每页以 --- Page N --- 标记）：
{combined}

请严格输出以下JSON格式，不要包含其他内容：
{{"title": "文档标题（根内容推测）", "toc": [{{"level": 1, "title": "章节标题", "page": N}}]}}

要求：
- level 从 1 开始，1=最高级（章），2=节，3=子节
- page 必须对应 --- Page N --- 中的 N（PDF实际页码，从1开始）
- 标题文本保持原文，不要添加额外编号
- 如果文档没有清晰章节结构，toc 返回空数组 []"""


def validate_toc_data(data: dict) -> list[dict]:
    """
    验证 DeepSeek 返回的目录数据格式是否正确。
    返回清理后的 toc 列表，跳过无效条目。
    """
    toc = data.get("toc", [])
    if not isinstance(toc, list):
        return []

    valid = []
    for item in toc:
        if not isinstance(item, dict):
            continue
        level = item.get("level")
        title = item.get("title")
        page = item.get("page")

        if not isinstance(level, int) or level < 1:
            continue
        if not title or not isinstance(title, str):
            continue
        if not isinstance(page, int) or page < 1:
            continue

        valid.append({
            "level": min(level, 5),  # 最多支持5级
            "title": title.strip(),
            "page": page,
        })

    return valid


def analyze_pdf_structure(
    pages_text: list[dict],
    api_key: str,
    model: str = "deepseek-chat",
    max_retries: int = 2,
) -> dict:
    """
    调用 DeepSeek API 分析 PDF 结构，提取目录。

    参数:
        pages_text: extract_text_by_page() 的返回值
        api_key: DeepSeek API Key
        model: 模型名称，默认 deepseek-chat
        max_retries: API 调用失败时的重试次数

    返回:
        {"title": str, "toc": [{"level": int, "title": str, "page": int}, ...]}

    异常:
        当 API 连续失败或返回格式严重错误时抛出异常
    """
    if not api_key:
        raise ValueError("DeepSeek API Key 不能为空")
    if not pages_text:
        raise ValueError("没有可分析的文本内容")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
    )

    user_prompt = build_user_prompt(pages_text)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=4096,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("API 返回内容为空")

            result = json.loads(content)

            # 验证并清理 toc 数据
            valid_toc = validate_toc_data(result)
            if valid_toc:
                return {
                    "title": result.get("title", "未命名文档"),
                    "toc": valid_toc,
                    "raw_count": len(result.get("toc", [])),
                    "valid_count": len(valid_toc),
                }
            elif attempt < max_retries:
                # 可能是格式问题，重试
                continue
            else:
                return {
                    "title": result.get("title", "未命名文档"),
                    "toc": [],
                    "raw_count": 0,
                    "valid_count": 0,
                }

        except json.JSONDecodeError as e:
            last_error = f"JSON 解析失败: {e}"
            time.sleep(1)

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(2)

    raise Exception(f"DeepSeek API 调用失败（已重试 {max_retries} 次）: {last_error}")


def create_fallback_toc(pages_text: list[dict]) -> dict:
    """
    备用方案：当 API 不可用时，用简单规则提取可能的标题。
    目前只做占位，实际可扩展为基于字体大小/样式的启发式提取。
    """
    return {"title": "（API不可用，无法分析）", "toc": []}
