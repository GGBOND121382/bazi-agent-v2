# 前端架构

## 层次

```text
pages → feature components → view models → generated API client
                        ↘ presentational components
```

- Page 负责路由参数、查询和编排；
- Feature component 负责一个业务交互；
- ViewModel mapper 将后端 DTO 转成展示数据；
- UI component 不知道 API；
- 图表组件只接受已经计算的 series 和文本替代。

## 状态

### TanStack Query

Chart、Job、Analysis、Report、History、Settings 等服务端状态。

### Pinia

仅用于：
- 侧栏开合；
- 专业/简洁模式；
- 临时筛选；
- 非敏感表单步骤状态；
- 用户界面偏好。

### URL

当前 chart、year、month、selected dayun、report section 应可链接和刷新恢复。

## 运行时校验

生成 TypeScript 类型不等于运行时安全。关键边界响应使用生成的 JSON Schema validator 或 Zod adapter 校验；Schema 不支持时进入“客户端版本不兼容”错误页，不猜字段。
