from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import AutoTradingControl, Heartbeat, MarketSnapshot, OrderEvent, TradePlan
from .service import DecisionService
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
store = Store(settings.database_path)
decision_service = DecisionService(settings, store)


def require_ea_key(x_ea_key: Annotated[str | None, Header()] = None) -> None:
    if settings.ea_api_key.startswith("change-me"):
        raise HTTPException(status_code=503, detail="EA_API_KEY is not configured")
    if not x_ea_key or not hmac.compare_digest(x_ea_key, settings.ea_api_key):
        raise HTTPException(status_code=401, detail="invalid EA key")


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if settings.admin_api_token.startswith("change-me"):
        raise HTTPException(status_code=503, detail="ADMIN_API_TOKEN is not configured")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.admin_api_token):
        raise HTTPException(status_code=401, detail="invalid admin token")


async def scheduler() -> None:
    while True:
        await asyncio.sleep(settings.analysis_interval_seconds)
        snapshot_data = store.latest("snapshots")
        if not snapshot_data:
            continue
        latest_plan = store.latest("plans", snapshot_data["account"]["account_id"])
        if latest_plan:
            plan_time = datetime.fromisoformat(latest_plan["issued_at"])
            if (datetime.now(timezone.utc) - plan_time).total_seconds() < settings.analysis_interval_seconds:
                continue
        try:
            await decision_service.create_plan(MarketSnapshot.model_validate(snapshot_data))
        except Exception:
            logger.exception("scheduled analysis failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(scheduler())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="WiseFX AI API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["https://ai.mt4mt5.trade", "http://localhost:1899", "http://127.0.0.1:1899"], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-EA-Key", "X-Admin-Token"])


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "ai_provider": settings.ai_provider, "ai_configured": bool(settings.ai_api_key), "safe_mode": store.get_setting("auto_trading", str(settings.auto_trading_enabled).lower()) != "true"}


@app.post("/api/v1/ea/heartbeat", dependencies=[Depends(require_ea_key)])
def heartbeat(payload: Heartbeat) -> dict:
    store.save_heartbeat(json.loads(payload.model_dump_json()))
    server_auto = store.get_setting("auto_trading", str(settings.auto_trading_enabled).lower()) == "true"
    return {"accepted": True, "server_time": datetime.now(timezone.utc).isoformat(), "auto_trading_enabled": server_auto}


@app.post("/api/v1/market/snapshot", response_model=TradePlan, dependencies=[Depends(require_ea_key)])
async def market_snapshot(payload: MarketSnapshot) -> TradePlan:
    if payload.quote.ask < payload.quote.bid:
        raise HTTPException(status_code=422, detail="ask must be >= bid")
    store.save_snapshot(json.loads(payload.model_dump_json()))
    return await decision_service.create_plan(payload)


@app.post("/api/v1/analysis/request", response_model=TradePlan, dependencies=[Depends(require_ea_key)])
async def analysis_request(account_id: str = Query(..., min_length=1)) -> TradePlan:
    snapshot_data = store.latest("snapshots", account_id)
    if not snapshot_data:
        raise HTTPException(status_code=404, detail="no market snapshot")
    return await decision_service.create_plan(MarketSnapshot.model_validate(snapshot_data))


@app.get("/api/v1/trade-plans/latest", dependencies=[Depends(require_ea_key)])
def latest_plan(account_id: str = Query(..., min_length=1)) -> dict:
    plan = store.latest("plans", account_id)
    if not plan:
        raise HTTPException(status_code=404, detail="no trade plan")
    expires = datetime.fromisoformat(plan["expires_at"])
    plan["expires_in_seconds"] = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
    if plan["expires_in_seconds"] <= 0:
        plan["auto_trading_enabled"] = False
        plan["status"] = "OBSERVE"
    return plan


@app.post("/api/v1/order-events", dependencies=[Depends(require_ea_key)])
def order_event(payload: OrderEvent) -> dict:
    return {"accepted": store.save_order_event(json.loads(payload.model_dump_json())), "event_id": payload.event_id}


@app.get("/api/v1/dashboard/overview")
def dashboard_overview(account_id: str | None = None) -> dict:
    started = time.perf_counter()
    snapshot = store.latest("snapshots", account_id)
    plan = store.latest("plans", account_id)
    heartbeat_data = store.latest_heartbeat(account_id)
    now = datetime.now(timezone.utc)
    heartbeat_online = False
    if heartbeat_data:
        received = datetime.fromisoformat(heartbeat_data["server_received_at"])
        heartbeat_online = (now - received).total_seconds() < 90
    server_auto = store.get_setting("auto_trading", str(settings.auto_trading_enabled).lower()) == "true"
    account = snapshot["account"] if snapshot else {"account_id": "等待 EA 连接", "balance": 0, "equity": 0, "free_margin": 0, "daily_pnl": 0, "drawdown_pct": 0}
    quote = snapshot["quote"] if snapshot else {"symbol": "XAUUSD", "bid": 0, "ask": 0, "spread": 0, "atr": 0}
    decision = plan or {"action": "HOLD", "confidence": 0, "threshold": settings.min_confidence, "reason": "等待 EA 上传行情快照后启动 AI 分析。", "status": "WAITING_DATA", "long_votes": 0, "neutral_votes": 0, "short_votes": 0, "plan_id": "—"}
    return {
        "updated_at": now.isoformat(),
        "account": {"id": account["account_id"], **{key: account.get(key, 0) for key in ["balance", "equity", "free_margin", "daily_pnl", "drawdown_pct"]}},
        "quote": quote,
        "decision": {key: decision.get(key) for key in ["action", "confidence", "threshold", "reason", "status", "long_votes", "neutral_votes", "short_votes", "plan_id"]},
        "position": snapshot.get("position") if snapshot else None,
        "system": {"ea_online": heartbeat_online, "ai_provider": settings.ai_provider, "ai_configured": bool(settings.ai_api_key), "auto_trading": server_auto, "latency_ms": int((time.perf_counter()-started)*1000), "last_heartbeat": heartbeat_data.get("server_received_at") if heartbeat_data else None},
    }


@app.post("/api/v1/control/auto-trading", dependencies=[Depends(require_admin)])
def auto_trading(payload: AutoTradingControl) -> dict:
    if payload.enabled and not settings.allow_web_enable:
        raise HTTPException(status_code=403, detail="web enabling is disabled; set ALLOW_WEB_ENABLE=true after simulation validation")
    if payload.enabled and payload.confirmation != "I UNDERSTAND":
        raise HTTPException(status_code=422, detail="explicit confirmation required")
    store.set_setting("auto_trading", str(payload.enabled).lower())
    return {"auto_trading_enabled": payload.enabled}


project_root = Path(__file__).resolve().parents[2]
web_dist = project_root / "web" / "dist" / "client"
if web_dist.exists():
    app.mount("/_next", StaticFiles(directory=web_dist / "_next"), name="next-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        target = web_dist / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(web_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def frontend_not_built() -> dict:
        return {"message": "Frontend not built. Run npm run build in web/."}
