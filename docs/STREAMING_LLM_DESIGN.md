# DeepSeek 整体流式分析设计

## 目标

完整报告继续由一次统一上下文调用完成，避免把原局、六亲、健康和各步大运拆成彼此独立、可能结论冲突的分析。流式只改变传输方式，不改变模型看到的整体输入。

## 主调用

```text
紧凑确定性命盘 + 完整大运 + 输出契约
                    ↓
DeepSeek V4-Pro thinking（单次 SSE 流）
                    ↓
reasoning_content / content 分别累计
                    ↓
收到 [DONE] 后解析完整 JSON
                    ↓
Schema + 确定性规则 + 核心专题覆盖校验
```

- `reasoning_content` 是 DeepSeek API 显式返回的 provider reasoning；它与最终 JSON 分开保存。
- 正式报告只使用最终 `content` 中的完整 JSON。
- 未收到 `[DONE]`、连接中断、JSON 截断或无效时，不会保存半份报告。

## 超时与重试

- 连接超时：15 秒。
- 写入超时：60 秒。
- 流式空闲超时：90 秒，指连续 90 秒没有收到任何数据。
- 单次调用总期限：600 秒。
- 传输失败最多尝试 2 次；流式请求不能从中间 token 续传，因此重试会重新发送同一个完整请求。
- `finish_reason=length` 映射为 `MODEL_OUTPUT_TRUNCATED`，不当作普通网络错误重试。

## 局部修复

第一次分析始终是完整统一分析。只有本地校验失败后，系统才尝试定位目标字段：

- `kinship_assessment`
- `health_assessment`
- `dayun_assessment`
- `claims`
- `structure_assessment`
- `temporal_assessment`
- `reasoning_summary`
- `executive_summary`
- `reflection`

局部修复请求根据错误类型与 JSON 路径投影最小事实闭包，只携带错误块、冻结的全局结构结论、少量一致性相邻块及必要原局/岁运事实。模型只能返回受限 `analysis-json-patch-v2`；未列入 `allowed_paths` 的字段被冻结。无法安全定位的跨章节矛盾才回退为完整修订。

## 进度

后端根据流式事件记录同阶段心跳：

- 连接模型
- 整体推理
- 生成结构化报告
- 传输中断，自动重试
- 模型输出完成

第一轮模型调用约映射至 55%～73%，验证为 75%；局部修复约映射至 78%～88%，报告组装为 90%。所有进度保持单调，不会在自动修订时倒退到 55%。

## 可审计轨迹

报告和问答轨迹保存：

- 模型与 Prompt 版本；
- 实际输入与本次 JSON Schema；
- provider `reasoning_content`；
- 最终 JSON；
- token usage；
- 首个 chunk 延迟与总耗时；
- 传输尝试次数与 `finish_reason`；
- 程序规则验证、程序 Reflection、局部修复目标和合并后的候选报告。

不会记录 DeepSeek API Key、Cookie 或密码。
