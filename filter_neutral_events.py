#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除 summaryList 中 tag 为「中性」的事件，输出结构保持不变。

用法::

    python filter_neutral_events.py input.json > output.json
    cat input.json | python filter_neutral_events.py
    python filter_neutral_events.py input.json -o output.json --renumber-priority

也可以直接作为模块调用::

    from filter_neutral_events import filter_neutral_events
    result = filter_neutral_events(data)
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from typing import Any

SUMMARY_KEY = "summaryList"
NEUTRAL_TAG = "中性"

# 模型输出的 tag 可能带有引号、空格或「中性偏多」这类后缀，先做归一化再判断。
_STRIP_CHARS = " \t\r\n\u3000\"'`[]（）()【】「」『』<>《》,，.。;；:：/、|-—_*#"


def _normalize_tag(value: Any) -> str:
    """把 tag 归一化成便于比较的字符串；非字符串一律返回空串。"""
    if not isinstance(value, str):
        return ""
    # NFKC 可以把全角字符折叠成半角，避免「ｔａｇ」之类的宽字符干扰。
    return unicodedata.normalize("NFKC", value).strip(_STRIP_CHARS)


def is_neutral(item: Any) -> bool:
    """判断单条事件是否为中性事件。

    只有 tag 明确表示中性时才返回 True：缺失 tag、tag 为空或无法识别的条目
    都会被保留，避免误删有效数据。
    """
    if not isinstance(item, dict):
        return False
    tag = _normalize_tag(item.get("tag"))
    if not tag:
        return False
    # 覆盖「中性」「中立」以及「中性偏多」「中性/观望」等变体写法。
    return tag.startswith(NEUTRAL_TAG) or tag.startswith("中立")


def filter_summary_list(
    summary_list: Any,
    renumber_priority: bool = False,
) -> list[Any]:
    """过滤事件列表，返回剔除中性事件后的新列表（不修改入参）。"""
    if not isinstance(summary_list, list):
        raise TypeError(f"{SUMMARY_KEY} 必须是数组，实际为 {type(summary_list).__name__}")

    kept = [item for item in summary_list if not is_neutral(item)]
    if not renumber_priority:
        return kept

    result = []
    for index, item in enumerate(kept, start=1):
        if isinstance(item, dict) and "priority" in item:
            item = {**item, "priority": index}
        result.append(item)
    return result


def filter_neutral_events(data: Any, renumber_priority: bool = False) -> Any:
    """删除中性事件，保持输入的整体结构不变。

    支持两种入参形态：

    * 完整对象 ``{"summaryList": [...], ...}``：返回同样的对象结构，
      ``summaryList`` 之外的字段与顺序原样保留。
    * 裸数组 ``[...]``：返回过滤后的数组。
    """
    if isinstance(data, dict):
        if SUMMARY_KEY not in data:
            raise KeyError(f"输入对象缺少 {SUMMARY_KEY} 字段")
        return {
            key: filter_summary_list(value, renumber_priority) if key == SUMMARY_KEY else value
            for key, value in data.items()
        }
    return filter_summary_list(data, renumber_priority)


def filter_neutral_events_json(text: str, renumber_priority: bool = False, indent: int = 2) -> str:
    """JSON 字符串进、JSON 字符串出，方便直接串在模型输出后面使用。"""
    result = filter_neutral_events(json.loads(text), renumber_priority)
    return json.dumps(result, ensure_ascii=False, indent=indent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="删除 summaryList 中 tag=中性 的事件")
    parser.add_argument("input", nargs="?", help="输入 JSON 文件，缺省时从标准输入读取")
    parser.add_argument("-o", "--output", help="输出 JSON 文件，缺省时写到标准输出")
    parser.add_argument(
        "--renumber-priority",
        action="store_true",
        help="删除后把 priority 重新按 1..N 编号（默认保留原值）",
    )
    parser.add_argument("--indent", type=int, default=2, help="输出缩进，0 表示压缩成一行")
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()

    try:
        output = filter_neutral_events_json(
            text,
            renumber_priority=args.renumber_priority,
            indent=args.indent or None,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"处理失败：{error}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
