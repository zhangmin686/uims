# Dify 代码节点：过滤中性事件

用于【资讯分类和总结】LLM 节点之后，删除 `tag = 中性` 的资讯，输出结构与上游保持一致。

代码见 [`filter_neutral_news.py`](./filter_neutral_news.py)，把文件内容整段粘贴到 Dify「代码执行」节点（Python3）即可。

## 节点位置

```
资讯分类和总结（LLM） → 过滤中性事件（代码节点） → 下游节点
```

## 入参配置

代码节点「输入变量」只需要一个：

| 变量名 | 类型 | 取值 |
| --- | --- | --- |
| `llm_output` | String | 上游 LLM 节点的输出，例如 `{{#资讯分类和总结.text#}}` |

上游输出为 JSON 字符串、对象、对象数组、被 ```` ```json ```` 包裹的文本时都能解析；解析失败按“无有效结果”处理，不会抛异常中断工作流。

## 出参配置

代码节点「输出变量」按下表逐个声明，变量名必须与代码返回的键一致：

| 变量名 | 类型 | 说明 |
| --- | --- | --- |
| `result` | Object | 保留时为上游原结构对象；被过滤时为 `{}` |
| `result_json` | String | `result` 的 JSON 字符串，供直接拼接文案使用 |
| `results` | Array[Object] | 上游一次返回多条时的保留列表；单条场景为 0 或 1 个元素 |
| `kept_count` | Number | 保留条数 |
| `dropped_count` | Number | 丢弃条数（中性事件 + 空对象 `{}`） |
| `tag` | String | 保留结果的 `tag`；被过滤时为空字符串 |

只关心单条结果时，下游取 `result` 或 `result_json` 即可，其余输出变量可以不声明。

## 过滤规则

1. 上游输出 `{}`（盘中行情异动、无法归类）→ 丢弃。
2. `tag` 归一化后命中中性词表（`中性`、`中立`、`混合`、`无法判断`、`neutral`、`mixed` 等）→ 丢弃。归一化会去掉首尾空白、全角空格、引号并转小写，因此 `" 中性 "`、`"中性"` 等写法都能命中。
3. `tag` 为 `正向` / `负向`（含 `利好` / `利空` / `positive` / `negative`）→ 保留。
4. `tag` 缺失或是词表外的取值 → 默认按中性丢弃，由 `DROP_WHEN_TAG_MISSING = False` 改为保留。

## 结构保障

保留的结果会按固定顺序重建，确保下游拿到的结构始终一致：

```json
{
  "summary": "",
  "newsId": "",
  "title": "",
  "publishTime": "",
  "publisher": "",
  "label": "",
  "newsType": "",
  "stockList": [{ "symbol": "", "name": "", "market": "" }],
  "tag": ""
}
```

- 缺失字段补空字符串，多余字段丢弃；
- `stockList` 每项只保留 `symbol`、`name`、`market`，并按上游提示词要求最多保留 4 只（`MAX_STOCK_COUNT`）。

## 下游按是否保留分支

代码节点之后接「条件分支」，用 `kept_count` 等于 `0` 判断该条资讯已被过滤，走空分支；否则走正常分支。

## 本地验证

```bash
python3 dify/filter_neutral_news.py
```

会打印中性、正向、`{}`、数组批量、脏数据五组样例的过滤结果。
