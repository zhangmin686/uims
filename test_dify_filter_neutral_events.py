#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dify_filter_neutral_events 的单元测试：python3 -m unittest -v

其中 DifySandboxContractTest 模拟 Dify 沙箱的执行方式，
确保代码粘贴进代码节点后能按预期运行。
"""

import ast
import json
import unittest

import dify_filter_neutral_events as node
from dify_filter_neutral_events import is_neutral, main

OUTPUT_KEYS = {"summaryList", "result", "keptCount", "removedCount", "error"}
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


class IsNeutralTest(unittest.TestCase):
    def test_recognizes_neutral_variants(self):
        for tag in ["中性", " 中性 ", "中性\n", "「中性」", "中性偏多", "中性/观望", "中立", "　中性　"]:
            with self.subTest(tag=tag):
                self.assertTrue(is_neutral({"tag": tag}))

    def test_keeps_positive_and_negative(self):
        for tag in ["正向", "负向", " 正向 ", "负向偏空"]:
            with self.subTest(tag=tag):
                self.assertFalse(is_neutral({"tag": tag}))

    def test_missing_or_invalid_tag_is_not_neutral(self):
        for item in [{}, {"tag": None}, {"tag": ""}, {"tag": 0}, {"tag": ["中性"]}, "不是对象"]:
            with self.subTest(item=item):
                self.assertFalse(is_neutral(item))


class MainFilteringTest(unittest.TestCase):
    def test_removes_only_neutral_items(self):
        output = main(
            summaryList=[
                make_item("600519", "正向", 1),
                make_item("000001", "中性", 2),
                make_item("300750", "负向", 3),
                make_item("601318", "中性", 4),
            ]
        )

        self.assertEqual([item["symbol"] for item in output["summaryList"]], ["600519", "300750"])
        self.assertEqual(output["keptCount"], 2)
        self.assertEqual(output["removedCount"], 2)
        self.assertEqual(output["error"], "")

    def test_item_fields_and_order_unchanged(self):
        item = make_item("600519", "正向", 7)
        output = main(summaryList=[item, make_item("000001", "中性")])

        self.assertEqual(output["summaryList"][0], item)
        self.assertEqual(list(output["summaryList"][0].keys()), ITEM_KEYS)

    def test_result_keeps_wrapper_structure(self):
        output = main(summaryList=[make_item("600519", "正向"), make_item("000001", "中性")])
        result = json.loads(output["result"])

        self.assertEqual(list(result.keys()), ["summaryList"])
        self.assertEqual(len(result["summaryList"]), 1)
        self.assertIn("正向", output["result"])
        self.assertNotIn("中性", output["result"])

    def test_object_input_preserves_sibling_keys(self):
        output = main(summaryList={"requestId": "abc-123", "summaryList": [make_item("000001", "中性")], "total": 1})
        result = json.loads(output["result"])

        self.assertEqual(list(result.keys()), ["requestId", "summaryList", "total"])
        self.assertEqual(result["requestId"], "abc-123")
        self.assertEqual(result["summaryList"], [])

    def test_does_not_mutate_input(self):
        data = {"summaryList": [make_item("600519", "正向", 1), make_item("000001", "中性", 2)]}
        snapshot = json.dumps(data, ensure_ascii=False, sort_keys=True)

        main(summaryList=data, renumberPriority="true")

        self.assertEqual(json.dumps(data, ensure_ascii=False, sort_keys=True), snapshot)

    def test_priority_preserved_by_default(self):
        output = main(summaryList=[make_item("000001", "中性", 1), make_item("600519", "正向", 2)])

        self.assertEqual([item["priority"] for item in output["summaryList"]], [2])

    def test_priority_renumbered_on_request(self):
        items = [make_item("000001", "中性", 1), make_item("600519", "正向", 2), make_item("300750", "负向", 3)]

        for flag in ["true", "True", "1", 1, "是", True]:
            with self.subTest(flag=flag):
                output = main(summaryList=items, renumberPriority=flag)
                self.assertEqual([item["priority"] for item in output["summaryList"]], [1, 2])

    def test_empty_and_all_neutral_lists(self):
        empty = main(summaryList=[])
        self.assertEqual(empty["summaryList"], [])
        self.assertEqual(empty["error"], "")

        all_neutral = main(summaryList=[make_item("000001", "中性"), make_item("600519", "中性")])
        self.assertEqual(all_neutral["summaryList"], [])
        self.assertEqual(all_neutral["removedCount"], 2)


class InputShapeTest(unittest.TestCase):
    def test_accepts_json_string(self):
        text = json.dumps({"summaryList": [make_item("600519", "中性"), make_item("300750", "负向")]}, ensure_ascii=False)
        output = main(text=text)

        self.assertEqual([item["symbol"] for item in output["summaryList"]], ["300750"])
        self.assertEqual(output["removedCount"], 1)

    def test_accepts_fenced_llm_output(self):
        body = json.dumps({"summaryList": [make_item("600519", "中性"), make_item("300750", "正向")]}, ensure_ascii=False)
        output = main(text="```json\n%s\n```" % body)

        self.assertEqual(output["keptCount"], 1)
        self.assertEqual(output["error"], "")

    def test_extracts_json_embedded_in_prose(self):
        body = json.dumps({"summaryList": [make_item("300750", "正向")]}, ensure_ascii=False)
        output = main(text="好的，以下是结果：\n%s\n希望对你有帮助。" % body)

        self.assertEqual(output["keptCount"], 1)
        self.assertEqual(output["error"], "")

    def test_falls_back_to_unknown_variable_name(self):
        output = main(arg1=[make_item("600519", "正向"), make_item("000001", "中性")])

        self.assertEqual(output["keptCount"], 1)
        self.assertEqual(output["error"], "")


class ErrorHandlingTest(unittest.TestCase):
    def test_reports_error_instead_of_raising(self):
        for bad in [None, "不是 JSON", {"list": []}, {"summaryList": "not a list"}, 123]:
            with self.subTest(bad=bad):
                output = main(summaryList=bad)
                self.assertNotEqual(output["error"], "")
                self.assertEqual(output["summaryList"], [])
                self.assertEqual(set(output), OUTPUT_KEYS)

    def test_raises_when_strict_mode_enabled(self):
        node.RAISE_ON_ERROR = True
        try:
            with self.assertRaises(ValueError):
                main(text="不是 JSON")
        finally:
            node.RAISE_ON_ERROR = False


class DifySandboxContractTest(unittest.TestCase):
    """校验代码符合 Dify 代码节点/沙箱的约束。"""

    def test_only_imports_stdlib_json(self):
        with open(node.__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())

        imported = set()
        for statement in ast.walk(tree):
            if isinstance(statement, ast.Import):
                imported.update(alias.name for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom):
                imported.add(statement.module)

        self.assertEqual(imported, {"json"})

    def test_has_no_top_level_side_effects(self):
        """Dify 会把整段代码当作 __main__ 执行，顶层不能有执行逻辑。"""
        with open(node.__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())

        allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.Expr)
        for statement in tree.body:
            self.assertIsInstance(statement, allowed)
            if isinstance(statement, ast.Expr):
                self.assertIsInstance(statement.value, ast.Constant)  # 只允许文档字符串

    def test_output_is_json_serializable_dict(self):
        output = main(summaryList=[make_item("600519", "正向"), make_item("000001", "中性")])

        self.assertIsInstance(output, dict)
        self.assertEqual(set(output), OUTPUT_KEYS)
        self.assertIsInstance(output["summaryList"], list)
        self.assertIsInstance(output["result"], str)
        self.assertIsInstance(output["keptCount"], int)
        self.assertIsInstance(output["removedCount"], int)
        self.assertIsInstance(output["error"], str)
        json.dumps(output, indent=4)

    def test_output_nesting_within_five_levels(self):
        """Dify 限制对象/数组嵌套不超过 5 层。"""

        def depth(value):
            if isinstance(value, dict):
                return 1 + max([depth(item) for item in value.values()] or [0])
            if isinstance(value, list):
                return 1 + max([depth(item) for item in value] or [0])
            return 0

        self.assertLessEqual(depth(main(summaryList=[make_item("600519", "正向")])), 5)

    def test_runs_through_dify_runner_template(self):
        """按 Dify 的模板执行：粘贴代码 -> main(**inputs) -> json.dumps 打印。"""
        with open(node.__file__, encoding="utf-8") as handle:
            source = handle.read()

        namespace = {"__name__": "__main__"}
        exec(compile(source, "<dify-code-node>", "exec"), namespace)

        inputs = {"summaryList": [make_item("600519", "正向"), make_item("000001", "中性")]}
        output_obj = namespace["main"](**json.loads(json.dumps(inputs)))
        printed = json.dumps(output_obj, indent=4)

        self.assertEqual(len(json.loads(printed)["summaryList"]), 1)


if __name__ == "__main__":
    unittest.main()
