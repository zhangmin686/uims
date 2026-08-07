#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filter_neutral_events 的单元测试：python3 -m unittest -v"""

import json
import unittest

from filter_neutral_events import (
    filter_neutral_events,
    filter_neutral_events_json,
    is_neutral,
)


def make_item(symbol, tag, priority=1):
    return {
        "symbol": symbol,
        "market": "SH",
        "name": f"股票{symbol}",
        "summary": f"{symbol} 净利润同比增长 35.2%，全年营收 12.8 亿元",
        "priority": priority,
        "tag": tag,
        "label": "业绩相关",
    }


class IsNeutralTest(unittest.TestCase):
    def test_recognizes_neutral_variants(self):
        for tag in ["中性", " 中性 ", "中性\n", "「中性」", "中性偏多", "中性/观望", "中立"]:
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


class FilterNeutralEventsTest(unittest.TestCase):
    def test_removes_only_neutral_items(self):
        data = {
            "summaryList": [
                make_item("600519", "正向", 1),
                make_item("000001", "中性", 2),
                make_item("300750", "负向", 3),
                make_item("601318", "中性", 4),
            ]
        }
        result = filter_neutral_events(data)

        self.assertEqual([item["symbol"] for item in result["summaryList"]], ["600519", "300750"])
        self.assertEqual([item["tag"] for item in result["summaryList"]], ["正向", "负向"])

    def test_output_structure_and_fields_unchanged(self):
        item = make_item("600519", "正向", 7)
        result = filter_neutral_events({"summaryList": [item, make_item("000001", "中性")]})

        self.assertEqual(list(result.keys()), ["summaryList"])
        self.assertEqual(result["summaryList"][0], item)
        self.assertEqual(
            list(result["summaryList"][0].keys()),
            ["symbol", "market", "name", "summary", "priority", "tag", "label"],
        )

    def test_preserves_sibling_keys(self):
        data = {"requestId": "abc-123", "summaryList": [make_item("000001", "中性")], "total": 1}
        result = filter_neutral_events(data)

        self.assertEqual(list(result.keys()), ["requestId", "summaryList", "total"])
        self.assertEqual(result["summaryList"], [])
        self.assertEqual(result["requestId"], "abc-123")

    def test_does_not_mutate_input(self):
        data = {"summaryList": [make_item("600519", "正向"), make_item("000001", "中性")]}
        snapshot = json.dumps(data, ensure_ascii=False, sort_keys=True)

        filter_neutral_events(data)

        self.assertEqual(json.dumps(data, ensure_ascii=False, sort_keys=True), snapshot)

    def test_accepts_bare_list(self):
        result = filter_neutral_events([make_item("600519", "正向"), make_item("000001", "中性")])

        self.assertIsInstance(result, list)
        self.assertEqual([item["symbol"] for item in result], ["600519"])

    def test_priority_preserved_by_default(self):
        data = {"summaryList": [make_item("000001", "中性", 1), make_item("600519", "正向", 2)]}

        self.assertEqual([item["priority"] for item in filter_neutral_events(data)["summaryList"]], [2])

    def test_priority_renumbered_on_request(self):
        data = {
            "summaryList": [
                make_item("000001", "中性", 1),
                make_item("600519", "正向", 2),
                make_item("300750", "负向", 3),
            ]
        }
        result = filter_neutral_events(data, renumber_priority=True)

        self.assertEqual([item["priority"] for item in result["summaryList"]], [1, 2])

    def test_empty_and_all_neutral_lists(self):
        self.assertEqual(filter_neutral_events({"summaryList": []})["summaryList"], [])
        all_neutral = {"summaryList": [make_item("000001", "中性"), make_item("600519", "中性")]}
        self.assertEqual(filter_neutral_events(all_neutral)["summaryList"], [])

    def test_rejects_bad_input(self):
        with self.assertRaises(KeyError):
            filter_neutral_events({"list": []})
        with self.assertRaises(TypeError):
            filter_neutral_events({"summaryList": "not a list"})


class JsonHelperTest(unittest.TestCase):
    def test_json_round_trip_keeps_chinese_readable(self):
        text = json.dumps(
            {"summaryList": [make_item("600519", "中性"), make_item("300750", "负向")]},
            ensure_ascii=False,
        )
        output = filter_neutral_events_json(text)

        self.assertIn("负向", output)
        self.assertNotIn("中性", output)
        self.assertEqual(len(json.loads(output)["summaryList"]), 1)


if __name__ == "__main__":
    unittest.main()
