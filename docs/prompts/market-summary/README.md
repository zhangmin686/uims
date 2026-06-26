# 大盘总结 Prompt 工程包

本目录包含「自选早晚报」产品中 **大盘总结** 模块的完整提示词工程资产。

## 目录结构

```
market-summary/
├── README.md                    # 本文件
├── 大盘总结工作流设计.md        # 完整设计文档（含流程、评估维度）
├── system.md                    # System Prompt（核心原则 + 禁止事项）
├── user.md                      # User Prompt（含思考步骤 + 输出要求）
├── schema.json                  # JSON Schema（用于结构化输出校验）
└── example-implementation.py    # 参考实现（预处理 + Prompt 构建 + 校验）
```

## 快速开始

1. 把 `newsList` JSON 字符串传入 `generate_market_summary()`
2. 实现 `call_llm()` 中的真实模型调用（必须支持 JSON mode）
3. 运行后得到符合 schema 的输出

## 当前状态

- ✅ 输入输出契约已明确
- ✅ 基础 System / User Prompt 已编写
- ✅ Schema + 预处理 + 校验逻辑已提供
- ⏳ **等待 3 篇真实示例** → 用于风格校准和 Few-shot 构建

## 收到示例后的迭代流程

1. 把 3 篇示例分别保存为 `examples/good-01.json`、`good-02.json`、`good-03.json`
2. 运行 `analyze_examples.py`（待补充）进行结构拆解
3. 根据拆解结果更新：
   - `system.md`（是否需要补充领域规则）
   - `user.md`（是否需要调整思考步骤、长度、语气）
   - `大盘总结工作流设计.md`（补充真实拆解结论）
4. 在 `user.md` 中加入 1-2 个 Few-shot 示例
5. 更新 `schema.json` 约束（如需要）
6. 补充 golden test cases

## 质量目标（人工 + 自动）

| 维度         | 目标分 | 说明 |
|--------------|--------|------|
| 事实忠实度   | ≥9/10  | 所有论据必须能在输入中找到 |
| 大盘视角     | ≥8.5/10| 避免个股化、事件化 |
| 信息密度     | ≥8/10  | 每句话都有实质信息 |
| 标题质量     | ≥8/10  | 准确 + 有吸引力 |
| 结构清晰度   | ≥8.5/10| 逻辑递进、段落分明 |

---

**下一步**：请把 3 篇参考生成结果示例直接贴到对话中，我会立即拆解并产出校准版本。
