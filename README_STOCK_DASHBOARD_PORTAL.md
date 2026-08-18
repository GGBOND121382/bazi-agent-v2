# AS1455 看板与执行 API 接入统一门户

该接入同时保留两个 AS1455 外部入口：

```text
http://服务器:8000/stock/           -> 127.0.0.1:8501
http://服务器:8000/stock-exec-api/  -> 127.0.0.1:8510
```

部署后结构：

```text
/
├── /bazi/
├── /zhongyi/
├── /stock/
└── /stock-exec-api/
```

`/stock/` 是 Streamlit 看板，通过八字系统的 `bazi_session` Cookie 调用 `/api/v1/auth/me` 做访问认证。未登录用户会跳转到八字登录页，登录后返回股票看板。

`/stock-exec-api/` 是手机 AS1455 执行批次拉取入口。Nginx 会去掉该前缀并代理到 `127.0.0.1:8510`，原样转发 `Authorization`。该入口不使用 Bazi Cookie 鉴权，而由 AS1455 execution API 自身校验 `Authorization: Bearer $AS1455_EXECUTION_API_TOKEN`。

例如：

```text
/stock-exec-api/health
    -> 127.0.0.1:8510/health

/stock-exec-api/api/v1/execution/latest?experiment=...
    -> 127.0.0.1:8510/api/v1/execution/latest?experiment=...
```

## 前置条件

服务器已有：

```text
~/bazi-agent-v2
~/stock_realtime_v021_full
```

对应分支：

```text
bazi-agent-v2:            agent/mobile-ui-deterministic-chat
stock_realtime_v021_full: agent/ch17-as1455-clean
```

并且已经运行过 `deploy-dual-services.sh`，现有门户文件和 Nginx 站点为：

```text
/var/www/dual-agents/index.html
/etc/nginx/sites-available/dual-agents-8000
```

股票工程需要已有 `.venv_as1455`。

## 一键部署股票看板

```bash
cd ~/stock_realtime_v021_full
git switch agent/ch17-as1455-clean
git pull --ff-only

cd ~/bazi-agent-v2
git switch agent/mobile-ui-deterministic-chat
git pull --ff-only

sudo bash deploy-stock-dashboard-to-portal.sh
```

脚本会：

1. 安装 Streamlit 看板依赖；
2. 重新构建八字前端，使登录页支持登录后返回 `/stock/`；
3. 创建 `/etc/as1455-dashboard.env`；
4. 创建并启动 `as1455-dashboard.service`；
5. 给门户增加“AS1455 策略看板”入口；
6. 使用统一的 `scripts/as1455_portal_nginx.py` 写入 `/stock/` 和 `/stock-exec-api/` 两条路由；
7. 检查 Streamlit 健康状态和 Nginx 配置；
8. 失败时恢复原门户、八字前端静态文件、Nginx、systemd unit 和环境文件。

脚本可重复执行。已有刷新口令默认保留；重复运行不会重复插入门户卡片或 Nginx 配置。

## `update-all` 与 AS1455 路由

`deploy-dual-services.sh` 会重建双智能体门户和 Nginx 主站配置。AS1455 看板已经部署过后，日常更新仍使用：

```bash
cd ~/bazi-agent-v2
./manage-dual-services.sh update-all
```

`update-all` 最终执行的 `deploy-dual-services.sh` 会自动调用 `scripts/restore-stock-portal-if-present.sh`。该脚本会：

- 以已安装的 `as1455-dashboard.service` 作为 AS1455 门户接入标记；
- 如果 8501 看板正在运行，检查 `/stock/_stcore/health`；
- 探测 8510 execution API 的 `/health`，允许未带 token 时返回 `200` 或 `401`；
- 恢复门户首页的 AS1455 卡片；
- 恢复带 Bazi 登录鉴权的 `/stock/`；
- 恢复由 Bearer token 自身鉴权的 `/stock-exec-api/`；
- 执行 `nginx -t`、reload 和两条网关配置的 readiness 验证。

即使 8501 或 8510 某个上游暂时停止，已部署过的 Nginx 路由也会保留，不会因为下一次 `update-all` 被永久删除。

直接运行低层 `deploy-dual-services.sh` 也会自动调用同一恢复脚本，不需要再人工补 Nginx。

如需手工立即恢复当前服务器，可执行：

```bash
cd ~/bazi-agent-v2
git switch agent/mobile-ui-deterministic-chat
git pull --ff-only
bash scripts/restore-stock-portal-if-present.sh
```

## 自定义参数

默认参数：

```text
STOCK_PORT=8501
STOCK_BASE_PATH=stock
STOCK_EXEC_API_PORT=8510
STOCK_EXEC_API_BASE_PATH=stock-exec-api
```

需要修改时可在执行恢复/部署脚本前通过环境变量覆盖。

## 检查

看板：

```bash
curl -f http://127.0.0.1:8501/stock/_stcore/health
curl -I http://127.0.0.1:8000/stock/
```

执行 API：

```bash
curl -i \
  -H "Authorization: Bearer $AS1455_EXECUTION_API_TOKEN" \
  http://127.0.0.1:8510/health

curl -i \
  -H "Authorization: Bearer $AS1455_EXECUTION_API_TOKEN" \
  http://127.0.0.1:8000/stock-exec-api/health
```

完整 Nginx 检查：

```bash
sudo nginx -t
sudo nginx -T 2>/dev/null | grep -n -E 'stock|8510|8501'
```

浏览器访问股票看板：

```text
http://服务器IP:8000/stock/
```

手机执行器 API base URL：

```text
http://服务器IP:8000/stock-exec-api
```
