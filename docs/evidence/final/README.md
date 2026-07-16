# Final verification evidence

日期：2026-07-16；平台：Windows / Python 3.12 / system Chrome。

## 命令

```powershell
cd backend
py -m ruff check . --exclude .pytest_cache
py -m mypy app
py -m pytest -q
py -m pytest tests/contract -q
py -m pytest -m golden -q
py -m pytest tests/security tests/performance -q
py ../scripts/eval/run_boundary_eval.py

cd ../frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
npx playwright test
```

## 已记录结果

- ruff：All checks passed。
- mypy strict：55 个源文件无问题（mypy 2.3.0）。
- 全量 pytest：128/128；contract：36/36。
- Golden：4/4。
- security + performance：4/4。
- isolated evaluation reader：`total=6, valid_json=6`；未导入生产/RAG。
- Vitest：7/7。
- Playwright：14/14（desktop/mobile、axe、visual）；更新快照后无更新模式复跑 14/14。
- vue-tsc：0 errors；Vite production build passed。
- ESLint：0 errors / 0 warnings；OpenAPI → TypeScript 生成成功。
- RAG v2.1：27 个 manifest 哈希一致；自带校验器通过，SQLite 为 7,637 条生产记录。
- RAG / Agent 标记测试：21 项；覆盖三通道权限、多查询融合、引用与修订 Gate。
- DeepSeek 合成命盘完整在线 E2E 通过：正式 RAG → 结构化输出 → 确定性验证 passed → 报告生成。

全量 pytest、contract、lint 在最终交付前再次执行；若数字变化，以最终终端输出为准。
