# -*- coding: utf-8 -*-
"""Dify 代码节点：删除 summaryList 中 tag=中性 的事件，输出为 JSON 字符串。

节点配置：
    输入变量：news（String，接上游节点的 text 输出）
    输出变量：result（String）

Dify 会校验「已声明的输出变量个数 == 返回字典的键个数」，多返回一个键就会报
"Not all output parameters are validated."，所以这里只返回 result。
沙箱禁止文件系统与网络访问，故只用标准库 json；整段代码会先作为 __main__
执行再调用 main()，所以不要添加 if __name__ == "__main__": 之类的顶层逻辑。
"""

import json

SUMMARY_KEY = "summaryList"

# tag 归一化后以这些前缀开头即视为中性事件，可按业务口径增删。
NEUTRAL_PREFIXES = ("中性", "中立")

# tag 常带引号、空格或标点，比较前先剥掉。
_STRIP_CHARS = " \t\r\n\u3000\"'`[]()【】「」『』<>《》,.;:/、|-—_*#，。；：！？"

# 输出 JSON 的缩进，与上游文本格式保持一致；设为 None 则压成一行。
JSON_INDENT = 2

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


def is_neutral(item):
    """判断单条事件是否为中性事件。

    只有 tag 明确表示中性时才返回 True：缺失 tag、tag 为空或无法识别的条目
    都会被保留，避免误删有效数据。
    """
    if not isinstance(item, dict):
        return False
    tag = item.get("tag")
    if not isinstance(tag, str):
        return False
    tag = to_halfwidth(tag).strip(_STRIP_CHARS)
    # 覆盖「中性」「中立」以及「中性偏多」「中性/观望」等变体写法。
    return bool(tag) and tag.startswith(NEUTRAL_PREFIXES)


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
            return find_container(parse_json_text(value), depth + 1)
        except ValueError:
            return None

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


def filter_neutral_events(payload):
    """返回剔除中性事件后的容器对象。

    ``summaryList`` 之外的兄弟字段、以及每条事件的全部字段（包括
    title/publishTime/type 等 schema 之外的扩展字段）都原样保留，入参不被修改。
    """
    container = find_container(payload)
    if container is None:
        # 上游直接给了事件数组而不是带 summaryList 的对象。
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            container = {SUMMARY_KEY: payload}
        else:
            raise ValueError("未找到 %s，请检查上游节点的输出" % SUMMARY_KEY)

    output = {}
    for key, value in container.items():
        output[key] = [item for item in value if not is_neutral(item)] if key == SUMMARY_KEY else value
    return output


def main(news=None, **extras):
    payload = news
    if payload is None or payload == "":
        # 兼容输入变量取了别的名字（例如 arg1）的情况。
        for _, value in sorted(extras.items()):
            if value is not None and value != "":
                payload = value
                break
    if payload is None or payload == "":
        raise ValueError("未取到输入，请检查输入变量 news 是否已连线")

    container = filter_neutral_events(payload)
    return {"result": json.dumps(container, ensure_ascii=False, indent=JSON_INDENT)}
