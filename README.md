# WiseFX AI（智汇AI）v1.1

根据参考界面与前期设计文档实现的可运行 MVP，包含：

- React 19 前端：总览、行情、决策、复盘、风控。
- FastAPI 服务：EA 心跳、行情快照、AI 分析、计划轮询、订单事件、仪表盘。
- DeepSeek/OpenAI 兼容适配：Base URL、模型和 API Key 均可配置，使用 JSON Output。
- MT5 EA：定时上传行情、获取计划、本地硬风控、模拟/实盘双开关和订单回报。
- SQLite 审计存储、Docker 与 Windows 启动脚本。
- 官网首页、演示登录注册、管理员/会员 RBAC 权限管理。
- 手机端首页、登录弹窗、交易控制台底部导航和会员管理卡片布局。

## 演示账号

登录页已经默认填写管理员账号，也可以一键切换会员账号：

```text
管理员：admin@wisefx.ai / WiseFX@Admin11
会员：member@wisefx.ai / WiseFX@Member11
```

这些凭据仅用于开发演示。正式运营前必须设置 `DEMO_AUTH_ENABLED=false`，并接入邮箱验证、密码找回、登录限流和独立的初始管理员创建流程。

## 目录

```text
web/                 React/Vinext 前端
server/              FastAPI、AI 分析和 SQLite 数据
ea/mt5/              MT5 EA 源码与安装说明
scripts/             初始化、构建、启动、冒烟测试
前期设计/            需求、架构、API 和页面设计文档
```

## Windows 启动

```powershell
.\scripts\init-config.ps1
# 编辑 server/.env，填写 AI_API_KEY
.\scripts\build.ps1
.\scripts\start.ps1
```

服务绑定 `0.0.0.0:1899`：

- 控制台：`http://127.0.0.1:1899/`
- 健康检查：`http://127.0.0.1:1899/api/v1/health`
- API 文档：`http://127.0.0.1:1899/api/docs`

如 Nginx Proxy Manager 已把 `ai.mt4mt5.trade` 转发到本机 `1899`，无需额外前端跨域配置。建议启用 HTTPS，并关闭缓存与 WebSocket 选项无关；API 和页面使用同一域名。

访问首页后，未登录用户看到产品介绍与价格；登录后自动进入交易控制台。ADMIN 拥有用户和系统管理权限，MEMBER 当前为控制台只读权限。所有权限均由服务端 RBAC 校验。

## Docker 启动

```powershell
.\scripts\init-config.ps1
# 编辑 server/.env，填写 AI_API_KEY
docker compose up -d --build
```

## AI 配置

默认使用当前 DeepSeek OpenAI 兼容接口：

```dotenv
AI_PROVIDER=deepseek
AI_API_BASE=https://api.deepseek.com
AI_API_KEY=your-key
AI_MODEL=deepseek-v4-flash
```

也可以替换成其他 `/chat/completions` 兼容服务。AI Key 只保存在服务端，不进入浏览器或 EA。

## MT5 安装

参见 `ea/mt5/README.md`。EA 必须在 MT5 的 WebRequest 允许列表中加入 `https://ai.mt4mt5.trade`，并将 `server/.env` 中的 `EA_API_KEY` 填入 EA 参数。

## 安全默认值

- `AUTO_TRADING_ENABLED=false`
- `ALLOW_WEB_ENABLE=false`
- EA 的 `InpAllowAutoTrading=false`
- EA 的 `InpAllowLiveAccount=false`
- 未配置或调用失败时，AI 固定降级为 `HOLD`

不要直接跳过模拟盘。启用自动交易至少需要：服务端开关、EA 本地开关、有效 AI 计划和所有本地硬风控同时通过。

## 官方接口依据

- DeepSeek Chat Completions：<https://api-docs.deepseek.com/api/create-chat-completion/>
- DeepSeek JSON Output：<https://api-docs.deepseek.com/guides/json_mode/>
- MQL5 WebRequest：<https://www.mql5.com/en/docs/network/webrequest>
