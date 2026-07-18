# Fortune Chat Prompt V6：分层继承与上下文投影

## 目标

问答模型必须完整遵循：

```text
原局 → 大运 → 流年 → 流月 → 流日
```

V6 不通过删除上层背景来缩短 Prompt，而是将完整确定性快照投影为一份不重复的模型 Context：

- 流年：原局 + 当前大运 + 目标流年 + 12 个精简流月窗口；
- 流月：原局 + 当前大运 + 目标流年 + 目标流月；
- 流日：原局 + 当前大运 + 目标流年 + 目标流月 + 目标流日；
- 大运：原局 + 起运 + 目标大运 + 大运序列摘要；
- 生命周期：原局 + 起运 + 全部大运。

## 三种数据用途分离

1. `deterministic_snapshot`：完整命盘、全部计算字段和规则溯源，仅保存在生成轨迹中；
2. `analysis_context`：当前 `topic + scope` 所需的模型输入；
3. `evidence`：RAG 解释证据，排除已经由确定性引擎给出的十神查表结果。

## 模型输入结构

```json
{
  "query": {
    "question": "今年的感情机会",
    "scope": "year",
    "topics": ["relationship"],
    "target_date": "2026-07-18"
  },
  "analysis_context": {
    "context_version": "bazi-fortune-chat-context-v3",
    "context_policy": "deterministic_read_only",
    "natal_core": {},
    "topic_context": {},
    "temporal_hierarchy": {}
  },
  "evidence": [],
  "output_profile": "fortune-chat-json-v2"
}
```

`evidence` 和 `conversation_history` 为空时不输出。恒定策略不再以大组 `true/false` 重复发送，而由动态 system prompt 的 scope/topic 片段表达。

## 字段压缩原则

模型 Context 保留：

- 四柱、十神、藏干十神、月令/司令、五行、季节状态；
- 原局关系；
- 岁运柱的十神、藏干、神煞；
- 岁运柱与原局关系、跨层关系、`attention`、`variant`、非空 `basis`；
- 专题索引，如配偶星位置、夫妻宫、财星位置、官印食伤位置。

仅在审计快照保留：

- `rule_id`、`fact_id`；
- `source_title`、`source_locator`、`rule_version`；
- 经纬度、计算中间参数和重复展示字段；
- 不适用的 `null`、空字符串和空 `basis`。

已计算且“为空本身有意义”的数组仍保留，例如 `spouse_star_locations: []`，表示已检查但原局没有相应透藏位置。

## RAG 路由

检索词由用户问题动态生成：

- 感情问题只追加配偶星、夫妻宫及婚恋触发；
- 健康问题才追加寒暖燥湿、调候和脏腑；
- 生命周期问题才追加出生起运与全部大运；
- 流年问题不再默认检索流日；
- `PROJECT-CORE-RULES-V1` 中重复的十神查表证据不送模型。

## 验证

`tests/golden/test_fortune_prompt_projection_golden.py` 使用此前 12 个问真样例验证：

- 四柱完整保留；
- 指定神煞完整保留；
- 指定原局关系完整保留；
- 空藏干十神、规则来源元数据不进入模型 Context。

`tests/unit/test_chat_context.py` 验证所有 scope 的层级继承与停止位置。
