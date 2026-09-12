# API 与实时事件接口草案

Base URL：`/api/v1`  
时间：UTC ISO-8601  
金额/价格：JSON 字符串或 Decimal 序列化，避免浮点误差  
认证：EA 使用 HMAC；Web 使用 OIDC Access Token。

## 1. EA 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/ea/register` | 一次性绑定实例 |
| POST | `/ea/heartbeat` | 心跳、运行模式、健康状态 |
| POST | `/market/snapshots` | 上传行情/指标快照 |
| POST | `/analysis/requests` | 创建分析请求 |
| GET | `/analysis/requests/{request_id}` | 获取分析状态/计划 |
| POST | `/trade-plans/{plan_id}/ack` | EA 接受或拒绝计划 |
| POST | `/order-events/batch` | 批量补传订单事件 |
| POST | `/positions/sync` | 持仓/挂单对账 |
| GET | `/ea/config` | 获取只会收紧本地限制的远程配置 |

## 2. 创建分析请求

```json
{
  "request_id": "01J...ULID",
  "account_id": "acc_demo_001",
  "ea_instance_id": "ea_001",
  "symbol": "XAUUSD",
  "broker_symbol": "XAUUSD.a",
  "trigger": "NEW_BAR_M15",
  "market_timestamp": "2026-09-13T09:05:00Z",
  "quote": {"bid": "4348.20", "ask": "4348.53", "spread_points": 33},
  "timeframes": {
    "M15": {"bars_ref": "snap_001_m15", "atr": "18.69", "rsi": "42.1"},
    "H1": {"bars_ref": "snap_001_h1", "atr": "31.40", "adx": "27.2"}
  },
  "account": {"equity": "258785.92", "free_margin": "258786.00", "drawdown_pct": "0.00"},
  "positions": [],
  "strategy_version": "genesis-xau-0.1.0",
  "snapshot_sha256": "..."
}
```

返回：已命中缓存时 `200`；异步处理时 `202`。

```json
{
  "request_id": "01J...ULID",
  "status": "PROCESSING",
  "poll_after_ms": 1000,
  "expires_at": "2026-09-13T09:05:20Z"
}
```

## 3. TradePlan

```json
{
  "schema_version": "1.0",
  "plan_id": "plan_01J...",
  "request_id": "01J...ULID",
  "status": "ACTIONABLE",
  "action": "OPEN",
  "side": "SHORT",
  "symbol": "XAUUSD",
  "order_type": "MARKET",
  "entry_zone": {"min": "4347.80", "max": "4349.20"},
  "stop_loss": "4357.20",
  "take_profit": [
    {"price": "4338.00", "close_pct": 50},
    {"price": "4329.50", "close_pct": 50}
  ],
  "risk": {"risk_pct": "0.50", "max_volume": "0.65", "max_slippage_points": 30},
  "confidence": 0.72,
  "open_threshold": 0.65,
  "votes": {"long": 6, "neutral": 12, "short": 11},
  "reason_summary": "H4 趋势与短周期动能偏空，但 M15 反弹使入场时机仍需价格确认。",
  "counter_evidence": ["M15 动能转强", "接近关键支撑"],
  "data_timestamp": "2026-09-13T09:05:00Z",
  "issued_at": "2026-09-13T09:05:06Z",
  "expires_at": "2026-09-13T09:05:20Z",
  "model_version": "provider-model-2026-09",
  "strategy_version": "genesis-xau-0.1.0",
  "key_id": "plan-signing-2026-09",
  "signature": "base64url..."
}
```

若 `confidence < open_threshold`，返回 `status=OBSERVE` 和 `action=HOLD`，不得夹带可执行开仓参数。

## 4. EA 回执

```json
{
  "event_id": "evt_01J...",
  "plan_id": "plan_01J...",
  "idempotency_key": "acc_demo_001:plan_01J...:OPEN",
  "ea_timestamp": "2026-09-13T09:05:08Z",
  "result": "REJECTED",
  "reason_code": "SPREAD_LIMIT_EXCEEDED",
  "observed": {"spread_points": 48, "limit_points": 35}
}
```

标准原因码至少包括：`PLAN_EXPIRED`、`INVALID_SIGNATURE`、`DUPLICATE_PLAN`、`STALE_QUOTE`、`PRICE_OUTSIDE_ENTRY_ZONE`、`SPREAD_LIMIT_EXCEEDED`、`SLIPPAGE_LIMIT_EXCEEDED`、`RISK_LIMIT_EXCEEDED`、`MARGIN_INSUFFICIENT`、`MARKET_CLOSED`、`EA_HALTED`、`BROKER_REJECTED`。

## 5. Web 管理接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/dashboard/overview?account_id=` | 总览聚合数据 |
| GET | `/market/context?symbol=&timeframe=` | 行情页数据 |
| GET | `/decisions/{id}` | 决策、因子、证据与反证 |
| GET | `/trades` | 成交与分页筛选 |
| GET | `/performance` | 复盘统计和版本对比 |
| GET | `/risk/status` | 当前风险、额度和熔断状态 |
| PUT | `/risk/policies/{id}` | 修改策略，要求管理员/MFA |
| POST | `/controls/trading-mode` | 切换 OBSERVE/CONFIRM/AUTO |
| POST | `/controls/halt` | 暂停新开仓 |
| POST | `/controls/emergency-close` | 紧急平仓，双确认 |

所有写操作必须提交 `Idempotency-Key`、`reason` 和前端生成的 `correlation_id`。

## 6. WebSocket

连接：`wss://host/api/v1/stream?account_id=...`

事件主题：

- `system.health.changed`
- `market.quote.updated`（前端节流到 2–5 次/秒）
- `analysis.status.changed`
- `trade_plan.created`
- `risk_check.completed`
- `order.status.changed`
- `position.updated`
- `risk.alert.created`
- `control.mode.changed`

事件信封：

```json
{
  "event_id": "evt_01J...",
  "event_type": "order.status.changed",
  "account_id": "acc_demo_001",
  "occurred_at": "2026-09-13T09:05:09Z",
  "sequence": 18421,
  "trace_id": "trace_...",
  "data": {}
}
```

前端发现 sequence 跳号时调用 REST 增量补偿；断线重连不得假定本地状态仍然最新。

