# Genesis AI EA（MT5）

## 安装

1. 将 `GenesisAI_EA.mq5` 复制到 MT5 数据目录的 `MQL5/Experts/GenesisAI/`。
2. 用 MetaEditor 打开并编译。
3. MT5 → 工具 → 选项 → 智能交易系统，勾选允许 WebRequest，并添加：
   `https://ai.mt4mt5.trade`
4. 把服务端 `server/.env` 的 `EA_API_KEY` 填到 EA 参数 `InpEaApiKey`。
5. 先挂载到模拟账户的目标品种图表。默认 `InpAllowAutoTrading=false`，此时只分析、不下单。

## 开启交易的双开关

必须同时满足以下条件才可能发单：

- 服务端 `AUTO_TRADING_ENABLED=true`，或管理员 API 已开启。
- EA 参数 `InpAllowAutoTrading=true`。

真实账户还必须额外设置 `InpAllowLiveAccount=true`。AI 置信度、本地日亏损/回撤、点差、持仓数、入场偏差和交易商止损距离仍会逐项检查。

## 注意

- DeepSeek/API Key 只配置在服务端，不能写入 EA。
- `WebRequest` 是同步调用，因此分析放在 `OnTimer`，不放在 `OnTick`。
- Strategy Tester 不支持 `WebRequest`。回测需使用录制计划或本地适配器，不能调用真实 API。
- 当前为 MT5 MVP；投入实盘前需要针对具体交易商的 XAUUSD 合约规格做回放、模拟盘和小资金灰度。

