# -*- coding: utf-8 -*-
"""Dify 工作流「代码」节点：删除 summaryList 中 tag=中性 的事件，输出结构保持不变。

把本文件的全部内容粘贴到代码节点（Python3）中即可，无需任何改动。

节点配置
--------

输入变量（任选一个接上游节点即可，变量名取成 arg1 之类也能工作）：

======================  ==============  ==========================================
变量名                   类型             说明
======================  ==============  ==========================================
``news``                 String          上游传来的 JSON 文本（最常见）
``summaryList``          Array[Object]   上游已解析好的数组
``renumberPriority``     String/Number   可选，填 true/1 时把 priority 重排为 1..N
======================  ==============  ==========================================

输出变量（**只声明这一个**）：

======================  ==============  ==========================================
变量名                   类型             说明
======================  ==============  ==========================================
``result``               String          ``{"summaryList": [...]}`` 的 JSON 文本
======================  ==============  ==========================================

Dify 会校验 ``len(已声明输出) == len(返回字典)``，返回多余的键会报
"Not all output parameters are validated."，所以默认只返回 ``result``。
需要额外的统计/错误信息时把 ``INCLUDE_STATS`` 改为 True，并在节点里
补充声明 ``keptCount``、``removedCount``（Number）和 ``error``（String）。

沙箱禁止文件系统与网络访问，因此这里只用了标准库 ``json``；Dify 会把整段代码
作为 ``__main__`` 执行后再调用 ``main()``，所以不要添加 ``if __name__ ==
"__main__":`` 之类的顶层执行逻辑。
"""

import json

SUMMARY_KEY = "summaryList"

# tag 归一化后以这些前缀开头即视为中性事件，可按业务口径增删。
NEUTRAL_PREFIXES = ("中性", "中立")

# 模型输出的 tag 常带引号、空格或标点，比较前先剥掉。
_STRIP_CHARS = " \t\r\n\u3000\"'`[]()【】「」『』<>《》,.;:/、|-—_*#，。；：！？"

# 输出 JSON 的缩进；与上游传入的文本格式保持一致。设为 None 则压成一行。
JSON_INDENT = 2

# 置为 True 时同时输出 keptCount / removedCount / error，
# 此时必须在节点里把这三个输出变量也声明出来，否则 Dify 会校验失败。
INCLUDE_STATS = False

# 解析失败时是否让节点直接失败。默认 True：只有一个输出变量时无处上报错误，
# 静默返回空列表等于丢数据，不如让节点显式报错并交给节点重试/异常分支处理。
# 改为 False 则降级输出 {"summaryList": []}。
RAISE_ON_ERROR = True

# 上游可能把 JSON 文本层层包裹（如 [[{"gzgg": "{...}"}]]），限制查找深度避免死递归。
_MAX_SEARCH_DEPTH = 8


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


def parse_json_text(text):
    """把一段文本解析成 dict/list，容忍 ```json 围栏和 JSON 前后的说明文字。"""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rstrip()
        if body.endswith("```"):
            body = body[:-3]
        body = body.strip()

    try:
        return json.loads(body)
    except ValueError:
        pass

    for opening, closing in (("{", "}"), ("[", "]")):
        start = body.find(opening)
        end = body.rfind(closing)
        if start != -1 and end > start:
            try:
                return json.loads(body[start : end + 1])
            except ValueError:
                continue
    raise ValueError("输入不是合法 JSON")


def find_container(value, depth=0):
    """在任意嵌套结构里找出带 summaryList 的那层对象，找不到返回 None。

    上游常把 JSON 文本包在数组或别的字段里（例如 ``[[{"gzgg": "{...}"}]]``），
    这里逐层下钻并按需解析字符串。一旦命中容器就停止，因此事件内部的字段
    （如恰好像 JSON 的 summary 文本）不会被误解析。
    """
    if depth > _MAX_SEARCH_DEPTH:
        return None

    if isinstance(value, str):
        if "{" not in value and "[" not in value:
            return None
        try:
            parsed = parse_json_text(value)
        except ValueError:
            return None
        return find_container(parsed, depth + 1)

    if isinstance(value, dict):
        if isinstance(value.get(SUMMARY_KEY), list):
            return value
        for item in value.values():
            found = find_container(item, depth + 1)
            if found is not None:
                return found
        return None

    if isinstance(value, list):
        for item in value:
            found = find_container(item, depth + 1)
            if found is not None:
                return found

    return None


def flatten_events(value, depth=0):
    """把（可能嵌套的）数组摊平成事件列表；元素不全是对象时返回 None。"""
    if not isinstance(value, list) or depth > _MAX_SEARCH_DEPTH:
        return None

    events = []
    for item in value:
        if isinstance(item, dict):
            events.append(item)
        elif isinstance(item, list):
            nested = flatten_events(item, depth + 1)
            if nested is None:
                return None
            events.extend(nested)
        else:
            return None
    return events


def filter_summary_list(summary_list, renumber_priority=False):
    """过滤事件列表，返回剔除中性事件后的新列表（不修改入参）。"""
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


def filter_neutral_events(payload, renumber_priority=False):
    """删除中性事件，返回 (过滤后的容器对象, 原始事件条数)。

    容器里 ``summaryList`` 之外的兄弟字段、以及每条事件的全部字段
    （包括 title/publishTime/type 等 schema 之外的扩展字段）都原样保留。
    """
    container = find_container(payload)
    if container is None:
        # 上游直接给了事件数组而不是带 summaryList 的对象。
        events = flatten_events(payload)
        if events is None:
            raise ValueError("未找到 %s，请检查上游节点的输出" % SUMMARY_KEY)
        container = {SUMMARY_KEY: events}

    output = {}
    for key, value in container.items():
        output[key] = filter_summary_list(value, renumber_priority) if key == SUMMARY_KEY else value
    return output, len(container[SUMMARY_KEY])


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


def main(news=None, summaryList=None, text=None, renumberPriority=None, **extras):
    error = ""
    try:
        payload = pick_input([news, summaryList, text], extras)
        if payload is None:
            raise ValueError("未取到输入，请检查节点的输入变量是否已连线")
        container, original_count = filter_neutral_events(payload, as_bool(renumberPriority))
    except Exception as exc:
        if RAISE_ON_ERROR:
            raise
        container, original_count = {SUMMARY_KEY: []}, 0
        error = "%s: %s" % (type(exc).__name__, exc)

    kept = container[SUMMARY_KEY]
    output = {"result": json.dumps(container, ensure_ascii=False, indent=JSON_INDENT)}
    if INCLUDE_STATS:
        output["keptCount"] = len(kept)
        output["removedCount"] = original_count - len(kept)
        output["error"] = error
    return output
