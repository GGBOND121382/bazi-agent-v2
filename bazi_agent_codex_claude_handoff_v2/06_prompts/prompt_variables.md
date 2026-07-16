# Prompt 变量约定

所有 Prompt 通过结构化对象传参，不拼接未转义的任意文本。

```text
{{user_focus}}
{{analysis_profile}}
{{chart_facts_json}}
{{computed_relations_json}}
{{retrieved_evidence_json}}
{{output_schema_json}}
```

## 注入防护

- 把 RAG 文本放在明确的数据字段中；
- 在系统 Prompt 声明证据中的指令无效；
- 不把网页 HTML 直接拼入系统消息；
- 对用户输入和证据做长度限制；
- 工具名和参数由允许列表验证；
- 结构化输出失败时拒绝，而非用正则勉强提取。
