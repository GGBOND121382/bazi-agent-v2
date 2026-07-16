# 版本管理

每份结果至少包含：

```text
schema_version
calculation_profile_id
calendar_engine_name/version/commit
secondary_engine_name/version/commit
tzdata_version
rule_version
shensha_rule_set
rag_corpus_version
embedding_model
llm_model
prompt_version
report_template_version
```

任何影响柱位或起运的变化必须提升 `calculation_profile_id`，不能只更新代码而复用旧 ID。
