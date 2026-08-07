# -*- coding: utf-8 -*-
"""Dify 代码节点：过滤【资讯分类和总结】输出中 tag 为“中性”的事件。

用法见同目录 README.md。直接把本文件内容粘贴到 Dify 代码节点（Python3）即可。
"""

import ast
import json
import re

# 输出结构（顺序固定，缺失字段补空值）
RESULT_KEYS = (
    "summary",
    "newsId",
    "title",
    "publishTime",
    "publisher",
    "label",
    "newsType",
    "stockList",
    "tag",
)
STOCK_KEYS = ("symbol", "name", "market")

# 上游提示词约定：股票最多保留四只
MAX_STOCK_COUNT = 4

# tag 缺失或不可识别时是否按“中性”丢弃
DROP_WHEN_TAG_MISSING = True

NEUTRAL_TAGS = {
    "中性",
    "中立",
    "中性事件",
    "混合",
    "中性/混合",
    "无法判断",
    "未知",
    "neutral",
    "mixed",
    "unknown",
    "none",
    "null",
}
KEPT_TAGS = {"正向", "负向", "利好", "利空", "positive", "negative"}

_CODE_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_JSON_SPAN = re.compile(r"[\{\[].*[\}\]]", re.S)


def _strip_wrapper(text):
    """去掉 LLM 常见的 Markdown 代码围栏和首尾空白。"""
    return _CODE_FENCE.sub("", text).strip()


def _loads(text):
    """尽最大努力把文本解析成 dict / list，失败返回 None。"""
    candidates = [text]
    span = _JSON_SPAN.search(text)
    if span:
        candidates.append(span.group(0))
    for candidate in candidates:
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(candidate)
            except Exception:
                continue
            if isinstance(value, (dict, list)):
                return value
    return None


def parse_payload(payload):
    """把上游节点的输出统一成 list[dict]。

    兼容：单个对象、对象数组、JSON 字符串、被 Markdown 包裹的 JSON、
    以及 {"result": [...]} 这类外层包装。
    """
    if payload is None:
        return []
    if isinstance(payload, str):
        text = _strip_wrapper(payload)
        if not text:
            return []
        payload = _loads(text)
        if payload is None:
            return []
    if isinstance(payload, dict):
        # 外层包装，例如 {"data": {...}} / {"result": [...]}
        if not set(payload) & set(RESULT_KEYS):
            for key in ("result", "results", "data", "output", "items", "list"):
                if key in payload:
                    return parse_payload(payload[key])
        return [payload]
    if isinstance(payload, list):
        items = []
        for element in payload:
            items.extend(parse_payload(element))
        return items
    return []


def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def normalize_tag(tag):
    """归一化 tag，便于比较：去空白、去全角空格、转小写。"""
    return _text(tag).replace("\u3000", "").strip().strip("\"'").lower()


def is_neutral(item):
    tag = normalize_tag(item.get("tag"))
    if not tag:
        return DROP_WHEN_TAG_MISSING
    if tag in NEUTRAL_TAGS:
        return True
    if tag in KEPT_TAGS:
        return False
    return DROP_WHEN_TAG_MISSING


def normalize_stock_list(raw):
    if isinstance(raw, str):
        raw = _loads(_strip_wrapper(raw)) or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    stocks = []
    for stock in raw[:MAX_STOCK_COUNT]:
        if not isinstance(stock, dict):
            continue
        stocks.append({key: _text(stock.get(key)) for key in STOCK_KEYS})
    return stocks


def normalize_item(item):
    """按固定结构重建对象，丢弃多余字段，补齐缺失字段。"""
    result = {}
    for key in RESULT_KEYS:
        if key == "stockList":
            result[key] = normalize_stock_list(item.get(key))
        else:
            result[key] = _text(item.get(key)).strip()
    return result


def filter_neutral(payload):
    """过滤中性事件，返回 (保留列表, 丢弃条数)。"""
    kept, dropped = [], 0
    for item in parse_payload(payload):
        if not isinstance(item, dict) or not item:
            dropped += 1
            continue
        if is_neutral(item):
            dropped += 1
            continue
        kept.append(normalize_item(item))
    return kept, dropped


def main(llm_output):
    """Dify 代码节点入口。

    入参：
        llm_output (String)  上游【资讯分类和总结】LLM 节点的输出文本

    出参：
        result       (Object)         保留时为原结构对象，被过滤时为 {}
        result_json  (String)         result 的 JSON 字符串
        results      (Array[Object])  批量场景下的保留列表
        kept_count   (Number)         保留条数
        dropped_count(Number)         丢弃条数（含中性事件与空对象）
        tag          (String)         保留结果的 tag，被过滤时为空字符串
    """
    kept, dropped = filter_neutral(llm_output)
    first = kept[0] if kept else {}
    return {
        "result": first,
        "result_json": json.dumps(first, ensure_ascii=False),
        "results": kept,
        "kept_count": len(kept),
        "dropped_count": dropped,
        "tag": first.get("tag", ""),
    }


if __name__ == "__main__":
    samples = [
        # 中性事件：被过滤，输出 {}
        '{"summary":"某公司发布公告","newsId":"1","title":"t","publishTime":"2026-08-07 09:00",'
        '"publisher":"p","label":"公司动态","newsType":"1","stockList":[{"symbol":"600000","name":"a","market":"SH"}],"tag":"中性"}',
        # 正向事件：原样保留
        '```json\n{"summary":"公司公告获得重大订单","newsId":"2","title":"t2","publishTime":"2026-08-07 10:00",'
        '"publisher":"p2","label":"公司公告-重大订单","newsType":"2",'
        '"stockList":[{"symbol":"600001","name":"b","market":"SH"},{"symbol":"600002","name":"c","market":"SH"},'
        '{"symbol":"600003","name":"d","market":"SH"},{"symbol":"600004","name":"e","market":"SH"},'
        '{"symbol":"600005","name":"f","market":"SH"}],"tag":"正向"}\n```',
        # 上游已判定为盘中异动：{} 直接丢弃
        "{}",
        # 数组批量输入
        '[{"summary":"s1","newsId":"3","tag":"负向","label":"行业政策","stockList":[]},'
        '{"summary":"s2","newsId":"4","tag":"中性","label":"市场情绪","stockList":[]}]',
        # 脏数据
        "not a json",
    ]
    for sample in samples:
        print(json.dumps(main(sample), ensure_ascii=False))
