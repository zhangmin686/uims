#!/usr/bin/env python3
"""
大盘总结生成器 - 参考实现（伪代码 + 结构）
用途：自选早晚报产品中调用 LLM 生成大盘总结
"""

import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# ==================== 配置区 ====================
SYSTEM_PROMPT = open("system.md", encoding="utf-8").read()
USER_PROMPT_TEMPLATE = open("user.md", encoding="utf-8").read()

# 推荐模型（根据实际环境选择）
# LLM_CLIENT = get_openai_client()  # 或 anthropic / qwen / deepseek 等

MAX_NEWS = 12                 # 最多带入多少条新闻
MAX_CONTENT_CHARS = 700       # 单条新闻正文最多截取字符
TARGET_SUMMARY_MIN = 350
TARGET_SUMMARY_MAX = 650


# ==================== 数据结构 ====================
@dataclass
class NewsItem:
    newsId: str
    title: str
    content: str
    publishTime: str
    publisher: str


@dataclass
class MarketSummary:
    summary: str
    newsId: str
    title: str
    publishTime: str
    publisher: str


# ==================== 预处理 ====================
def parse_news_list(news_list_str: str) -> List[NewsItem]:
    """解析输入的 newsList JSON 字符串"""
    raw = json.loads(news_list_str)
    items = []
    for r in raw:
        items.append(NewsItem(
            newsId=str(r.get("newsId", "")),
            title=r.get("title", "").strip(),
            content=r.get("content", "").strip(),
            publishTime=r.get("publishTime", ""),
            publisher=r.get("publisher", ""),
        ))
    return items


def preprocess(news_items: List[NewsItem]) -> List[NewsItem]:
    """清洗、去重、截断、排序"""
    # 1. 过滤无效
    filtered = [n for n in news_items if len(n.content) > 30 and len(n.title) > 5]

    # 2. 简单去重（标题相似）
    seen = set()
    deduped = []
    for n in filtered:
        key = n.title[:20]  # 粗暴去重，可替换为语义相似度
        if key not in seen:
            seen.add(key)
            deduped.append(n)

    # 3. 按时间倒序（简单处理）
    deduped.sort(key=lambda x: x.publishTime or "", reverse=True)

    # 4. 限制数量 + 截断正文
    limited = deduped[:MAX_NEWS]
    for n in limited:
        if len(n.content) > MAX_CONTENT_CHARS:
            n.content = n.content[:MAX_CONTENT_CHARS] + "…"

    return limited


# ==================== Prompt 构建 ====================
def build_user_prompt(news_items: List[NewsItem], current_date: str) -> str:
    """把新闻列表渲染进 User Prompt"""
    lines = []
    for n in news_items:
        block = f"""【newsId: {n.newsId}】
标题：{n.title}
来源：{n.publisher}
发布时间：{n.publishTime}
正文：
{n.content}

---"""
        lines.append(block)

    rendered = USER_PROMPT_TEMPLATE.replace("{{current_date}}", current_date)
    rendered = rendered.replace("{{news_count}}", str(len(news_items)))
    rendered = rendered.replace("{{#news_items}}", "").replace("{{/news_items}}", "")
    # 简单替换，生产环境建议用 Jinja2
    rendered = rendered.replace("{{news_items}}", "\n".join(lines))  # 占位简化

    return rendered


# ==================== LLM 调用（需替换为真实客户端） ====================
def call_llm(system: str, user: str, temperature: float = 0.35) -> str:
    """
    这里替换为真实 LLM 调用。
    要求：必须开启 JSON mode / structured output。
    """
    # 示例（伪代码）：
    # response = LLM_CLIENT.chat.completions.create(
    #     model="gpt-4o-2024-08-06",
    #     messages=[
    #         {"role": "system", "content": system},
    #         {"role": "user", "content": user},
    #     ],
    #     temperature=temperature,
    #     response_format={"type": "json_object"},
    # )
    # return response.choices[0].message.content

    raise NotImplementedError("请接入真实 LLM 客户端")


# ==================== 后处理与校验 ====================
def validate_and_fix(result: Dict[str, Any], fallback_news_id: str) -> MarketSummary:
    """校验 + 兜底修复"""
    summary = (result.get("summary") or "").strip()
    title = (result.get("title") or "").strip()
    news_id = (result.get("newsId") or fallback_news_id).strip()
    publish_time = result.get("publishTime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    publisher = result.get("publisher") or "自选早晚报 · 大盘总结"

    # 长度兜底
    if len(summary) < 150:
        # 可触发重试或降级
        raise ValueError("summary 过短，可能生成失败")

    return MarketSummary(
        summary=summary,
        newsId=news_id,
        title=title,
        publishTime=publish_time,
        publisher=publisher,
    )


def generate_market_summary(news_list_str: str) -> MarketSummary:
    """主入口"""
    news_items = parse_news_list(news_list_str)
    cleaned = preprocess(news_items)

    if not cleaned:
        raise ValueError("无可用的新闻内容用于生成大盘总结")

    # 选择最具代表性的 newsId（第一条通常最新）
    representative_id = cleaned[0].newsId or "summary_" + datetime.now().strftime("%Y%m%d")

    current_date = datetime.now().strftime("%Y-%m-%d")
    user_prompt = build_user_prompt(cleaned, current_date)

    # 调用 LLM
    raw_output = call_llm(SYSTEM_PROMPT, user_prompt, temperature=0.35)

    # 解析
    try:
        result_dict = json.loads(raw_output)
    except json.JSONDecodeError:
        # 可在这里做一次修复重试
        raise ValueError("LLM 输出不是合法 JSON")

    # 校验修复
    summary = validate_and_fix(result_dict, representative_id)
    return summary


# ==================== 使用示例 ====================
if __name__ == "__main__":
    sample_input = json.dumps([
        {
            "newsId": "1211",
            "title": "沪指震荡收涨 成交额超万亿",
            "content": "今日A股市场震荡上行，沪指收涨0.8%，深成指涨1.2%，成交额突破1.1万亿元。北向资金净流入超80亿元。政策面消息刺激券商、银行板块走强...",
            "publishTime": "2026-06-25 16:30",
            "publisher": "财联社"
        }
    ], ensure_ascii=False)

    # summary = generate_market_summary(sample_input)
    # print(summary)
    print("请先实现 call_llm 函数后再运行完整流程。")
