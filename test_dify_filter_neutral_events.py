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
from dify_filter_neutral_events import is_neutral, main

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


def make_news_item(symbol, tag):
    """带 title/publishTime/type 等 schema 之外扩展字段的真实形态。"""
    item = make_item(symbol, tag)
    item.update({"title": "%s：向特定对象发行股票申请获深交所受理" % symbol, "publishTime": 1785988200, "type": "news"})
    return item


def wrap(items, indent=2, **siblings):
    """还原上游节点的输出：JSON 文本。"""
    payload = dict(siblings)
    payload["summaryList"] = items
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def parse_result(output):
    return json.loads(output["result"])


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


class OutputContractTest(unittest.TestCase):
    def test_result_is_a_json_string(self):
        output = main(news=wrap([make_item("600519", "正向")]))

        self.assertIsInstance(output["result"], str)
        self.assertEqual(set(output), {"result"})

    def test_result_keeps_structure_and_formatting(self):
        output = main(news=wrap([make_item("600519", "正向"), make_item("000001", "中性")]))

        # 与上游文本同样是 ensure_ascii=False + indent=2 的格式
        self.assertTrue(output["result"].startswith('{\n  "summaryList": [\n    {\n'))
        self.assertNotIn("\\u", output["result"])
        self.assertIn("正向", output["result"])
        self.assertNotIn("中性", output["result"])

        result = parse_result(output)
        self.assertEqual(list(result.keys()), ["summaryList"])
        self.assertEqual(list(result["summaryList"][0].keys()), ITEM_KEYS)

    def test_compact_output_when_indent_disabled(self):
        node.JSON_INDENT = None
        try:
            output = main(news=wrap([make_item("600519", "正向")]))
            self.assertNotIn("\n", output["result"])
        finally:
            node.JSON_INDENT = 2

    def test_stats_only_emitted_when_enabled(self):
        node.INCLUDE_STATS = True
        try:
            output = main(news=wrap([make_item("600519", "正向"), make_item("000001", "中性")]))
            self.assertEqual(set(output), {"result", "keptCount", "removedCount", "error"})
            self.assertEqual(output["keptCount"], 1)
            self.assertEqual(output["removedCount"], 1)
            self.assertEqual(output["error"], "")
        finally:
            node.INCLUDE_STATS = False


class FilteringTest(unittest.TestCase):
    def test_removes_only_neutral_items(self):
        output = main(
            news=wrap(
                [
                    make_item("600519", "正向", 1),
                    make_item("000001", "中性", 2),
                    make_item("300750", "负向", 3),
                    make_item("601318", "中性", 4),
                ]
            )
        )

        self.assertEqual([item["symbol"] for item in parse_result(output)["summaryList"]], ["600519", "300750"])

    def test_preserves_sibling_keys(self):
        output = main(news=wrap([make_item("000001", "中性")], requestId="abc-123", total=1))
        result = parse_result(output)

        self.assertEqual(sorted(result.keys()), ["requestId", "summaryList", "total"])
        self.assertEqual(result["requestId"], "abc-123")
        self.assertEqual(result["summaryList"], [])

    def test_preserves_extra_item_fields(self):
        output = main(news=wrap([make_news_item("300283", "中性"), make_news_item("300750", "正向")]))
        kept = parse_result(output)["summaryList"]

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["title"], "300750：向特定对象发行股票申请获深交所受理")
        self.assertEqual(kept[0]["publishTime"], 1785988200)
        self.assertEqual(kept[0]["type"], "news")

    def test_does_not_mutate_input(self):
        data = {"summaryList": [make_item("600519", "正向", 1), make_item("000001", "中性", 2)]}
        snapshot = json.dumps(data, ensure_ascii=False, sort_keys=True)

        main(news=data, renumberPriority="true")

        self.assertEqual(json.dumps(data, ensure_ascii=False, sort_keys=True), snapshot)

    def test_priority_preserved_by_default(self):
        output = main(news=wrap([make_item("000001", "中性", 1), make_item("600519", "正向", 2)]))

        self.assertEqual([item["priority"] for item in parse_result(output)["summaryList"]], [2])

    def test_priority_renumbered_on_request(self):
        payload = wrap([make_item("000001", "中性", 1), make_item("600519", "正向", 2), make_item("300750", "负向", 3)])

        for flag in ["true", "True", "1", 1, "是", True]:
            with self.subTest(flag=flag):
                output = main(news=payload, renumberPriority=flag)
                self.assertEqual([item["priority"] for item in parse_result(output)["summaryList"]], [1, 2])

    def test_empty_and_all_neutral_lists(self):
        self.assertEqual(parse_result(main(news=wrap([])))["summaryList"], [])

        all_neutral = main(news=wrap([make_item("000001", "中性"), make_item("600519", "中性")]))
        self.assertEqual(parse_result(all_neutral)["summaryList"], [])
        self.assertEqual(parse_result(all_neutral), {"summaryList": []})


class InputShapeTest(unittest.TestCase):
    def test_accepts_parsed_object_and_array(self):
        items = [make_item("600519", "正向"), make_item("000001", "中性")]

        for payload in [{"summaryList": items}, items]:
            with self.subTest(payload=type(payload).__name__):
                self.assertEqual(len(parse_result(main(news=payload))["summaryList"]), 1)

    def test_accepts_nested_wrapper_from_upstream_node(self):
        """真实日志形态：[[{"gzgg": "{...summaryList...}"}]]"""
        payload = [[{"gzgg": wrap([make_news_item("300283", "中性"), make_news_item("300750", "正向")])}]]
        kept = parse_result(main(news=payload))["summaryList"]

        self.assertEqual([item["symbol"] for item in kept], ["300750"])

    def test_accepts_fenced_llm_output(self):
        output = main(news="```json\n%s\n```" % wrap([make_item("600519", "中性"), make_item("300750", "正向")]))

        self.assertEqual(len(parse_result(output)["summaryList"]), 1)

    def test_extracts_json_embedded_in_prose(self):
        output = main(news="好的，以下是结果：\n%s\n希望对你有帮助。" % wrap([make_item("300750", "正向")]))

        self.assertEqual(len(parse_result(output)["summaryList"]), 1)

    def test_does_not_misparse_json_like_item_fields(self):
        item = make_item("600519", "正向")
        item["summary"] = '{"看起来像": "JSON 的摘要文本"}'
        kept = parse_result(main(news=wrap([item])))["summaryList"]

        self.assertEqual(kept[0]["summary"], '{"看起来像": "JSON 的摘要文本"}')

    def test_falls_back_to_unknown_variable_name(self):
        output = main(arg1=wrap([make_item("600519", "正向"), make_item("000001", "中性")]))

        self.assertEqual(len(parse_result(output)["summaryList"]), 1)


class ErrorHandlingTest(unittest.TestCase):
    def test_raises_by_default_so_the_node_fails_loudly(self):
        for bad in [None, "不是 JSON", {"list": []}, 123, ["不是对象"]]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    main(news=bad)

    def test_degrades_to_empty_list_when_configured(self):
        node.RAISE_ON_ERROR = False
        node.INCLUDE_STATS = True
        try:
            output = main(news="不是 JSON")
            self.assertEqual(parse_result(output), {"summaryList": []})
            self.assertNotEqual(output["error"], "")
        finally:
            node.RAISE_ON_ERROR = True
            node.INCLUDE_STATS = False


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
        allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.Expr)
        for statement in self._source_tree().body:
            self.assertIsInstance(statement, allowed)
            if isinstance(statement, ast.Expr):
                self.assertIsInstance(statement.value, ast.Constant)  # 只允许文档字符串

    def test_output_matches_declared_variable_count(self):
        """Dify 校验 len(已声明输出) == len(返回字典)，多余的键会导致节点失败。"""
        output = main(news=wrap([make_item("600519", "正向")]))

        self.assertEqual(set(output), {"result"})
        for value in output.values():
            self.assertIsInstance(value, str)
        json.dumps(output, indent=4)

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
