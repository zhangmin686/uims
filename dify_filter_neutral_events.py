# -*- coding: utf-8 -*-
"""Dify 代码节点：删除 summaryList 中 tag=中性 的事件，输出为 JSON 字符串。

节点配置：
    输入变量：news（String，接上游节点的 text 输出）
    输出变量：result（String）

Dify 会校验「已声明的输出变量个数 == 返回字典的键个数」，多返回一个键会报
"Not all output parameters are validated."，所以只返回 result。
"""

import json


def main(news) -> dict:
    data = news
    if isinstance(data, str):
        text = data.strip()
        if text.startswith("```"):  # LLM 常把 JSON 包在 ```json 围栏里
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(text)

    data = dict(data)
    data["summaryList"] = [
        item
        for item in data.get("summaryList", [])
        # startswith 兼容「中性偏多」这类写法；tag 缺失的条目一律保留，避免误删
        if not str(item.get("tag", "")).strip().startswith("中性")
    ]
    # ensure_ascii=False 否则中文会输出成 \u4e2d\u6027
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}
