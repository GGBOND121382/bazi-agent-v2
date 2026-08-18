# AS1455 看板接入统一门户

该脚本把 `stock_realtime_v021_full` 中的 Streamlit 看板接到现有智能体门户：

```text
http://服务器:8000/stock/
```

部署后结构：

```text
/
├── /bazi/
├── /zhongyi/
└── /stock/
```

`/stock/` 由 Nginx 反向代理到仅监听本机的 `127.0.0.1:8501`，并通过八字系统的 `bazi_session` Cookie 调用 `/api/v1/auth/me` 做访问认证。未登录用户会跳转到八字登录页，登录后返回股票看板。

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

## 一键部署

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
6. 给 Nginx 增加带登录认证的 `/stock/` 代理；
7. 检查 Streamlit 健康状态和 Nginx 配置；
8. 失败时恢复原门户、八字前端静态文件、Nginx、systemd unit 和环境文件。

脚本可重复执行。已有刷新口令默认保留；重复运行不会重复插入门户卡片或 Nginx 配置。

## `update-all` 与股票看板

`deploy-dual-services.sh` 会重建双智能体门户和 Nginx 主站配置。股票看板已经单独部署并处于健康状态时，日常更新应使用：

```bash
cd ~/bazi-agent-v2
./manage-dual-services.sh update-all
```

`update-all` 在完成双服务部署后会自动执行 `scripts/restore-stock-portal-if-present.sh`：

- 检测 `as1455-dashboard.service` 是否正在运行；
- 检查 `127.0.0.1:8501/stock/_stcore/health`；
- 恢复门户首页的 AS1455 卡片；
- 使用 `scripts/as1455_portal_nginx.py` 恢复带 Bazi 登录鉴权的 `/stock/` Nginx 路由；
- 执行 `nginx -t`、reload 和网关验证。

因此再次执行 `update-all` 不需要重新部署或重启 stock dashboard，也不会再把 `/stock/` 接入永久覆盖掉。

如果确实直接手工运行了低层的 `deploy-dual-services.sh`，可在其完成后执行一次：

```bash
bash scripts/restore-stock-portal-if-present.sh
```

该脚本是幂等的；未安装或未运行 stock dashboard 的机器会直接跳过。

## 自定义参数

```bash
sudo env \
  APP_USER="$USER" \
  BAZI_DIR="$HOME/bazi-agent-v2" \
  STOCK_DIR="$HOME/stock_realtime_v021_full" \
  PUBLIC_PORT=8000 \
  BAZI_API_PORT=8101 \
  ZHONGYI_PORT=8100 \
  STOCK_PORT=8501 \
  STOCK_BASE_PATH=stock \
  AS1455_DASHBOARD_REFRESH_TOKEN='替换为强口令' \
  bash deploy-stock-dashboard-to-portal.sh
```

脚本默认检查两个工程是否位于上述指定分支。确有需要时可以通过 `SKIP_BRANCH_CHECK=1` 跳过。

## 检查

```bash
sudo systemctl status as1455-dashboard nginx
curl -f http://127.0.0.1:8501/stock/_stcore/health
sudo nginx -t
```

浏览器访问：

```text
http://服务器IP:8000/
http://服务器IP:8000/stock/
```
