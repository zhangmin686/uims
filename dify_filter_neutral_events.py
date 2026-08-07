# -*- coding: utf-8 -*-
"""Dify 工作流「代码」节点：删除 summaryList 中 tag=中性 的事件，输出结构保持不变。

把本文件的全部内容粘贴到代码节点（Python3）中即可，无需任何改动。

节点配置
--------

输入变量（任选一个接上游节点即可，三种写法都支持）：

======================  ==============  ==========================================
变量名                   类型             说明
======================  ==============  ==========================================
``summaryList``          Array[Object]   上游已解析好的事件数组
``text``                 String          LLM 直接输出的 JSON 文本（可带 ```json 围栏）
``renumberPriority``     String/Number   可选，填 true/1 时把 priority 重排为 1..N
======================  ==============  ==========================================

若输入变量取了别的名字（例如 ``arg1``），代码也会自动取第一个非空入参，不会报错。

输出变量：

======================  ==============  ==========================================
变量名                   类型             说明
======================  ==============  ==========================================
``summaryList``          Array[Object]   过滤后的事件数组，结构与输入完全一致
``result``               String          ``{"summaryList": [...]}`` 的 JSON 文本
``keptCount``            Number          保留条数
``removedCount``         Number          删除条数
``error``                String          正常为空串，异常时为错误信息
======================  ==============  ==========================================

注意：沙箱禁止文件系统与网络访问，因此这里只用了标准库 ``json``；
Dify 会把整段代码作为 ``__main__`` 执行后再调用 ``main()``，所以不要添加
``if __name__ == "__main__":`` 之类的顶层执行逻辑。
"""

import json

SUMMARY_KEY = "summaryList"

# tag 归一化后以这些前缀开头即视为中性事件，可按业务口径增删。
NEUTRAL_PREFIXES = ("中性", "中立")

# 模型输出的 tag 常带引号、空格或标点，比较前先剥掉。
_STRIP_CHARS = " \t\r\n\u3000\"'`[]()【】「」『』<>《》,.;:/、|-—_*#，。；：！？"

# 置为 True 时解析失败直接抛异常让节点失败（便于配合节点重试）；
# 默认 False，改为通过 error 输出变量向下游传递错误。
RAISE_ON_ERROR = False


def to_halfwidth(text):
    """全角转半角。沙箱里不依赖 unicodedata，手动折叠 U+FF01-U+FF5E 与全角空格。"""
    chars = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(char)
    return "".join(chars)


def normalize_tag(value):
    """把 tag 归一化成便于比较的字符串；非字符串一律返回空串。"""
    if not isinstance(value, str):
        return ""
    return to_halfwidth(value).strip(_STRIP_CHARS)


def is_neutral(item):
    """判断单条事件是否为中性事件。

    只有 tag 明确表示中性时才返回 True：缺失 tag、tag 为空或无法识别的条目
    都会被保留，避免误删有效数据。
    """
    if not isinstance(item, dict):
        return False
    tag = normalize_tag(item.get("tag"))
    if not tag:
        return False
    # 覆盖「中性」「中立」以及「中性偏多」「中性/观望」等变体写法。
    return tag.startswith(NEUTRAL_PREFIXES)


def parse_payload(value):
    """把节点入参统一成 dict 或 list；字符串会按 JSON 解析。"""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise ValueError("输入类型不支持：%s" % type(value).__name__)

    text = value.strip()
    # LLM 常把 JSON 包在 ```json ... ``` 里。
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rstrip()
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except ValueError:
        pass

    # 兜底：JSON 前后混了说明文字时，截取最外层的 {...} 或 [...] 再试一次。
    for opening, closing in (("{", "}"), ("[", "]")):
        start = text.find(opening)
        end = text.rfind(closing)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                continue
    raise ValueError("输入不是合法 JSON")


def filter_summary_list(summary_list, renumber_priority=False):
    """过滤事件列表，返回剔除中性事件后的新列表（不修改入参）。"""
    if not isinstance(summary_list, list):
        raise ValueError("%s 必须是数组，实际为 %s" % (SUMMARY_KEY, type(summary_list).__name__))

    kept = [item for item in summary_list if not is_neutral(item)]
    if not renumber_priority:
        return kept

    result = []
    for index, item in enumerate(kept, start=1):
        if isinstance(item, dict) and "priority" in item:
            item = dict(item)
            item["priority"] = index
        result.append(item)
    return result


def filter_neutral_events(data, renumber_priority=False):
    """删除中性事件，保持输入的整体结构不变。

    入参可以是完整对象 ``{"summaryList": [...], ...}``（``summaryList`` 之外的
    字段原样保留），也可以是裸数组。
    """
    if isinstance(data, dict):
        if SUMMARY_KEY not in data:
            raise ValueError("输入对象缺少 %s 字段" % SUMMARY_KEY)
        output = {}
        for key, value in data.items():
            output[key] = filter_summary_list(value, renumber_priority) if key == SUMMARY_KEY else value
        return output
    return filter_summary_list(data, renumber_priority)


def as_bool(value, default=False):
    """Dify 输入变量只有字符串/数字，这里把常见的真值写法统一成 bool。"""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return to_halfwidth(value).strip().lower() in ("1", "true", "yes", "y", "on", "是")
    return default


def pick_input(candidates, extras):
    """按优先级挑出真正的数据入参，兼容用户把变量名取成 arg1 之类的情况。"""
    for value in candidates:
        if value is not None and value != "":
            return value
    for _, value in sorted(extras.items()):
        if value is not None and value != "":
            return value
    return None


def main(summaryList=None, text=None, renumberPriority=None, **extras):
    try:
        payload = pick_input([summaryList, text], extras)
        if payload is None:
            raise ValueError("未取到输入，请检查节点的输入变量是否已连线")

        parsed = parse_payload(payload)
        filtered = filter_neutral_events(parsed, as_bool(renumberPriority))
        if isinstance(filtered, dict):
            kept, wrapped, original = filtered[SUMMARY_KEY], filtered, parsed.get(SUMMARY_KEY) or []
        else:
            # 入参是裸数组时也按约定的结构包一层输出。
            kept, wrapped, original = filtered, {SUMMARY_KEY: filtered}, parsed
        original_count = len(original)
        error = ""
    except Exception as exc:  # 避免一条脏数据让整个工作流中断
        if RAISE_ON_ERROR:
            raise
        kept, wrapped, original_count = [], {SUMMARY_KEY: []}, 0
        error = "%s: %s" % (type(exc).__name__, exc)

    return {
        SUMMARY_KEY: kept,
        "result": json.dumps(wrapped, ensure_ascii=False),
        "keptCount": len(kept),
        "removedCount": original_count - len(kept),
        "error": error,
    }
