#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dify_filter_neutral_events 的单元测试：python3 -m unittest -v

其中 DifySandboxContractTest 模拟 Dify 沙箱的执行方式与输出校验规则，
确保代码粘贴进代码节点后能按预期运行。
"""

import ast
import json
import unittest

import dify_filter_neutral_events as node
from dify_filter_neutral_events import main

ITEM_KEYS = ["symbol", "market", "name", "summary", "priority", "tag", "label"]


def make_item(symbol, tag, priority=1):
    return {
        "symbol": symbol,
        "market": "SH",
        "name": "股票%s" % symbol,
        "summary": "%s 净利润同比增长 35.2%%，全年营收 12.8 亿元" % symbol,
        "priority": priority,
        "tag": tag,
        "label": "业绩相关",
    }


def wrap(items, **siblings):
    """还原上游节点 text 输出的形态：JSON 文本。"""
    payload = dict(siblings)
    payload["summaryList"] = items
    return json.dumps(payload, ensure_ascii=False, indent=2)


def kept_tags(output):
    return [item["tag"] for item in json.loads(output["result"])["summaryList"]]


class FilteringTest(unittest.TestCase):
    def test_removes_neutral_variants(self):
        for tag in ["中性", " 中性 ", "中性\n", "中性偏多", "中性/观望"]:
            with self.subTest(tag=tag):
                self.assertEqual(kept_tags(main(wrap([make_item("000001", tag)]))), [])

    def test_keeps_positive_and_negative(self):
        output = main(wrap([make_item("600519", "正向"), make_item("000001", "中性"), make_item("300750", "负向")]))

        self.assertEqual(kept_tags(output), ["正向", "负向"])

    def test_keeps_items_with_missing_or_odd_tag(self):
        items = [{"symbol": "600519"}, {"symbol": "000001", "tag": None}, {"symbol": "300750", "tag": ""}]

        self.assertEqual(len(json.loads(main(wrap(items))["result"])["summaryList"]), 3)

    def test_other_fields_untouched(self):
        item = make_item("600519", "正向", 7)
        item.update({"title": "半年报出炉", "publishTime": 1785988200, "type": "news"})
        output = main(wrap([make_item("000001", "中性"), item]))

        self.assertEqual(json.loads(output["result"])["summaryList"], [item])

    def test_preserves_sibling_keys(self):
        result = json.loads(main(wrap([make_item("000001", "中性")], requestId="abc-123", total=1))["result"])

        self.assertEqual(sorted(result.keys()), ["requestId", "summaryList", "total"])
        self.assertEqual(result["requestId"], "abc-123")
        self.assertEqual(result["summaryList"], [])

    def test_all_neutral_keeps_structure(self):
        output = main(wrap([make_item("000001", "中性"), make_item("600519", "中性")]))

        self.assertEqual(json.loads(output["result"]), {"summaryList": []})


class InputShapeTest(unittest.TestCase):
    def test_accepts_fenced_llm_output(self):
        output = main("```json\n%s\n```" % wrap([make_item("600519", "中性"), make_item("300750", "正向")]))

        self.assertEqual(kept_tags(output), ["正向"])

    def test_accepts_already_parsed_object(self):
        output = main({"summaryList": [make_item("600519", "正向"), make_item("000001", "中性")]})

        self.assertEqual(kept_tags(output), ["正向"])

    def test_does_not_mutate_parsed_input(self):
        data = {"summaryList": [make_item("600519", "正向"), make_item("000001", "中性")]}
        snapshot = json.dumps(data, ensure_ascii=False, sort_keys=True)

        main(data)

        self.assertEqual(json.dumps(data, ensure_ascii=False, sort_keys=True), snapshot)

    def test_fails_loudly_on_unusable_input(self):
        for bad in ["", "不是 JSON", None, 123]:
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError, TypeError)):
                    main(bad)


class DifySandboxContractTest(unittest.TestCase):
    """校验代码符合 Dify 代码节点/沙箱的约束。"""

    def _source_tree(self):
        with open(node.__file__, encoding="utf-8") as handle:
            return ast.parse(handle.read())

    def test_only_imports_stdlib_json(self):
        imported = set()
        for statement in ast.walk(self._source_tree()):
            if isinstance(statement, ast.Import):
                imported.update(alias.name for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom):
                imported.add(statement.module)

        self.assertEqual(imported, {"json"})

    def test_has_no_top_level_side_effects(self):
        """Dify 会把整段代码当作 __main__ 执行，顶层不能有执行逻辑。"""
        allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Expr)
        for statement in self._source_tree().body:
            self.assertIsInstance(statement, allowed)
            if isinstance(statement, ast.Expr):
                self.assertIsInstance(statement.value, ast.Constant)  # 只允许文档字符串

    def test_returns_exactly_one_string_variable(self):
        """节点只声明了 result（String）；键数不一致或类型不符都会让节点失败。"""
        output = main(wrap([make_item("600519", "正向")]))

        self.assertEqual(set(output), {"result"})
        self.assertIsInstance(output["result"], str)

    def test_output_format_matches_upstream_text(self):
        output = main(wrap([make_item("600519", "正向")]))

        self.assertTrue(output["result"].startswith('{\n  "summaryList": [\n    {\n'))
        self.assertNotIn("\\u", output["result"])
        self.assertIn("正向", output["result"])

    def test_runs_through_dify_runner_template(self):
        """按 Dify 的模板执行：粘贴代码 -> main(**inputs) -> json.dumps 打印。"""
        with open(node.__file__, encoding="utf-8") as handle:
            source = handle.read()

        namespace = {"__name__": "__main__"}
        exec(compile(source, "<dify-code-node>", "exec"), namespace)

        inputs = {"news": wrap([make_item("600519", "正向"), make_item("000001", "中性")])}
        output_obj = namespace["main"](**json.loads(json.dumps(inputs)))
        printed = json.dumps(output_obj, indent=4)

        self.assertEqual(len(json.loads(json.loads(printed)["result"])["summaryList"]), 1)


if __name__ == "__main__":
    unittest.main()
