"""
MiMo API 分析模块
=================
调用小米 MiMo API 分析 PDF 文本/图片结构，提取目录信息。
支持文字型 PDF（文本分析）和扫描件 PDF（视觉分析）。
"""

import json
import time
from openai import OpenAI

# ---------- MiMo 配置 ----------

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_VISION_MODEL = "mimo-v2.5"
MIMO_TEXT_MODEL = "mimo-v2.5"

# ---------- 文本分析提示词 ----------

SYSTEM_PROMPT = """你是一个专业的PDF文档目录提取助手。

任务：从PDF文本中提取**完整的章节目录结构**（Table of Contents）。

### 核心策略
首先在文本中查找"目录"、"Contents"、"目次"等标志性内容——这些是书的目录页。
如果找到了目录页内容，**从中提取全书完整的目录结构**（包含所有章节）。
如果没有目录页，则从正文中提取各章节标题。

### 你需要识别各级标题
- **一级标题**：章/部分，如 "第1章" "第一章" "Chapter 1" "Part I" 等
- **二级标题**：节标题，如 "1.1" "1.2" 等
- **三级标题**：子节标题，如 "1.1.1" 等

### 重要规则
1. 优先找目录页（"目录"、"Contents"），从中提取**完整**的章节列表
2. 只提取真正的章节结构，不要提取 "出版说明"、"前言"、"内容提要" 等
3. 标题必须有明确的编号体系
4. 宁缺毋滥"""


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

    return f"""请分析以下PDF每页的文本内容，提取文档的**完整章节目录**。

文本内容（每页以 --- Page N --- 标记）：
{combined}

请严格输出以下JSON格式，不要包含其他内容：
{{"title": "文档标题", "toc": [{{"level": 1, "title": "章节标题", "page": N}}]}}

### 核心策略
先在文本中查找"目录"、"Contents"段落——这是书的目录页。
**如果找到了目录内容，从中提取完整的全书章节列表（包括所有章节）。**
如果找不到目录页，再从正文中提取章节标题。

### 要求（非常重要）：
- level: 1=章/部分, 2=节, 3=子节
- page: 对应 --- Page N --- 中的N
- 章节标题必须有编号（如"第1章""1.1""一、""Chapter 2"等）
- 不要包含 "出版说明"、"前言"、"内容提要" 等非章节内容
- 如果文档没有清晰的章节结构，toc 返回空数组 []"""


def validate_toc_data(data: dict) -> list[dict]:
    """
    验证 MiMo 返回的目录数据格式是否正确。
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
    max_retries: int = 2,
) -> dict:
    """
    调用 MiMo API 分析 PDF 文本结构，提取目录。

    参数:
        pages_text: extract_text_by_page() 的返回值
        api_key: MiMo API Key
        max_retries: API 调用失败时的重试次数

    返回:
        {"title": str, "toc": [{"level": int, "title": str, "page": int}, ...]}

    异常:
        当 API 连续失败或返回格式严重错误时抛出异常
    """
    if not api_key:
        raise ValueError("API Key 不能为空")
    if not pages_text:
        raise ValueError("没有可分析的文本内容")

    client = OpenAI(
        api_key=api_key,
        base_url=MIMO_BASE_URL,
    )

    user_prompt = build_user_prompt(pages_text)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MIMO_TEXT_MODEL,
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

    raise Exception(f"MiMo API 调用失败（已重试 {max_retries} 次）: {last_error}")


def create_fallback_toc(pages_text: list[dict]) -> dict:
    """
    备用方案：当 API 不可用时，用简单规则提取可能的标题。
    目前只做占位，实际可扩展为基于字体大小/样式的启发式提取。
    """
    return {"title": "（API不可用，无法分析）", "toc": []}


# ---------- 扫描件支持：视觉分析 ----------

import re


def _extract_json(text: str) -> dict:
    """从 API 返回文本中健壮地提取 JSON，兼容各种包装格式"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError(f"无法从响应中提取 JSON。响应内容（前 300 字符）: {text[:300]}", text, 0)


VISION_PROMPT = """你只做一件事：从PDF截图中提取章节目录，只输出JSON。

我会依次发送PDF每一页的截图图片（按页码顺序）。

规则：
1. 优先找"目录"、"Contents"页，从中提取**全书完整**章节列表
2. 找不到目录页就从正文中提取章节标题
3. 只提取有编号的章节标题（"第1章""1.1""一、"等）
4. 忽略封面、出版说明、前言等非章节内容

⚠️ 输出格式要求：**只输出JSON，不要有任何其他文字、不要解释、不要分析过程**

{"title": "文档标题", "toc": [{"level": 1, "title": "第1章 xxx", "page": 3}]}"""


def analyze_pdf_vision(
    pdf_path: str,
    api_key: str,
    max_pages: int = 15,
    max_retries: int = 2,
) -> dict:
    """
    使用 MiMo 视觉 API 分析扫描件 PDF 结构，提取目录。
    如果发送页数过多导致失败，自动减少页数重试。

    参数:
        pdf_path: PDF 文件路径
        api_key: MiMo API Key
        max_pages: 最多分析页数
        max_retries: 每批次的 API 重试次数

    返回:
        {"title": str, "toc": [{"level": int, "title": str, "page": int}, ...]}
    """
    from pdf_toc import render_pdf_pages_base64

    if not api_key:
        raise ValueError("API Key 不能为空")

    client = OpenAI(
        api_key=api_key,
        base_url=MIMO_BASE_URL,
    )

    # 渐进式页数：先试目标页数，失败后减少
    page_budgets = [max_pages, 6]

    for budget_idx, budget in enumerate(page_budgets):
        # 渲染 PDF 页面为低分辨率图片（减小请求体积）
        pages = render_pdf_pages_base64(pdf_path, max_pages=budget, max_width=300)

        if not pages:
            raise ValueError("无法读取 PDF 页面")

        # 构建消息：文本指令 + 每页图片
        content = [{"type": "text", "text": VISION_PROMPT}]
        for p in pages:
            content.append({"type": "text", "text": f"\n--- Page {p['page_num']} ---"})
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{p['image_base64']}",
                },
            })

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=MIMO_VISION_MODEL,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.1,
                    max_tokens=8192,
                    stream=False,
                )

                # 调试：检查响应结构
                result_text = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                if result_text is None:
                    print(f"⚠️ MiMo 返回空内容，finish_reason={finish_reason}")
                    print(f"⚠️ 完整响应: {response}")
                    raise ValueError(f"API 返回空内容 (finish_reason={finish_reason})")

                if not result_text.strip():
                    raise ValueError("API 返回空字符串")

                # 尝试解析 JSON（兼容各种包装格式）
                try:
                    result = _extract_json(result_text)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"模型未返回 JSON，返回了自然语言文本。"
                        f"响应预览: {result_text[:200]}..."
                    )

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
                    continue
                else:
                    return {
                        "title": result.get("title", "未命名文档"),
                        "toc": [],
                        "raw_count": 0,
                        "valid_count": 0,
                    }

            except ValueError as e:
                # 模型返回了非 JSON 文本，重试也没用，直接跳到下一种页数方案
                last_error = str(e)
                break  # 跳出 retry 循环，进入下一个页数预算

            except Exception as e:
                last_error = str(e)
                # 打印更详细的错误
                if hasattr(e, 'response') and e.response is not None:
                    print(f"⚠️ API 错误: status={e.response.status_code}, body={e.response.text[:300]}")
                if attempt < max_retries:
                    print(f"⏳ 重试第 {attempt+2} 次...")
                    time.sleep(3)

        if budget_idx < len(page_budgets) - 1:
            print(f"⚠️ 发送 {budget} 页失败，减少到 {page_budgets[budget_idx+1]} 页重试...")
            time.sleep(1)

    raise Exception(f"MiMo 视觉 API 调用失败（已尝试 {len(page_budgets)} 种页数方案, 每方案重试 {max_retries+1} 次）: {last_error}")
