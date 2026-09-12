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

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import hash_password, issue_token, verify_password
from .config import settings
from .models import AdminUserUpdate, AutoTradingControl, Heartbeat, LoginRequest, MarketSnapshot, OrderEvent, RegisterRequest, TradePlan
from .service import DecisionService
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
store = Store(settings.database_path)
if settings.demo_auth_enabled:
    store.ensure_rbac([
        (settings.demo_admin_email, "演示管理员", settings.demo_admin_password, "ADMIN"),
        (settings.demo_member_email, "演示会员", settings.demo_member_password, "MEMBER"),
    ])
else:
    store.ensure_rbac([])
decision_service = DecisionService(settings, store)
SESSION_COOKIE = "wisefx_session"


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


def current_session(wisefx_session: Annotated[str | None, Cookie()] = None) -> tuple[dict, str]:
    if not wisefx_session:
        raise HTTPException(status_code=401, detail="请先登录")
    session = store.user_for_session(wisefx_session)
    if not session:
        raise HTTPException(status_code=401, detail="登录已失效")
    return session


def require_permission(permission: str):
    def dependency(session: tuple[dict, str] = Depends(current_session)) -> tuple[dict, str]:
        user, _ = session
        if permission not in user["permissions"]:
            raise HTTPException(status_code=403, detail="当前角色没有此权限")
        return session
    return dependency


def require_csrf(request: Request, session: tuple[dict, str] = Depends(current_session)) -> tuple[dict, str]:
    _, csrf_token = session
    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
    return session


def require_trade_control(
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
    wisefx_session: Annotated[str | None, Cookie()] = None,
) -> dict | None:
    if x_admin_token and not settings.admin_api_token.startswith("change-me") and hmac.compare_digest(x_admin_token, settings.admin_api_token):
        return None
    if not wisefx_session:
        raise HTTPException(status_code=401, detail="请先登录")
    session = store.user_for_session(wisefx_session)
    if not session:
        raise HTTPException(status_code=401, detail="登录已失效")
    user, csrf_token = session
    if "trading.control" not in user["permissions"]:
        raise HTTPException(status_code=403, detail="当前角色没有交易控制权限")
    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
    return user


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


app = FastAPI(title="WiseFX AI API", version="1.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["https://ai.mt4mt5.trade", "http://localhost:1899", "http://127.0.0.1:1899"], allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-EA-Key", "X-Admin-Token", "X-CSRF-Token"])


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "ai_provider": settings.ai_provider, "ai_configured": bool(settings.ai_api_key), "safe_mode": store.get_setting("auto_trading", str(settings.auto_trading_enabled).lower()) != "true"}


@app.post("/api/v1/auth/login")
def login(payload: LoginRequest, response: Response, request: Request) -> dict:
    record = store.get_user_by_email(payload.email.strip().lower())
    if not record or record["status"] != "ACTIVE" or not verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token, csrf_token = issue_token(), issue_token()
    store.create_session(record["id"], token, csrf_token, settings.session_hours)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_hours * 3600, httponly=True, secure=forwarded_proto == "https" or request.url.scheme == "https", samesite="lax", path="/")
    user = store.get_user(record["id"])
    return {"user": user, "csrf_token": csrf_token}


@app.post("/api/v1/auth/register", status_code=201)
def register(payload: RegisterRequest, response: Response, request: Request) -> dict:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="请输入有效邮箱")
    user = store.create_user(email, payload.name.strip(), hash_password(payload.password), "MEMBER")
    if not user:
        raise HTTPException(status_code=409, detail="该邮箱已经注册")
    token, csrf_token = issue_token(), issue_token()
    store.create_session(user["id"], token, csrf_token, settings.session_hours)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_hours * 3600, httponly=True, secure=forwarded_proto == "https" or request.url.scheme == "https", samesite="lax", path="/")
    return {"user": user, "csrf_token": csrf_token}


@app.get("/api/v1/auth/me")
def me(session: tuple[dict, str] = Depends(current_session)) -> dict:
    user, csrf_token = session
    return {"user": user, "csrf_token": csrf_token}


@app.post("/api/v1/auth/logout")
def logout(response: Response, wisefx_session: Annotated[str | None, Cookie()] = None, _: tuple[dict, str] = Depends(require_csrf)) -> dict:
    if wisefx_session:
        store.delete_session(wisefx_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"success": True}


@app.get("/api/v1/admin/users")
def admin_users(_: tuple[dict, str] = Depends(require_permission("users.manage"))) -> dict:
    return {"items": store.list_users()}


@app.patch("/api/v1/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: AdminUserUpdate, session: tuple[dict, str] = Depends(require_csrf)) -> dict:
    actor, _ = session
    if "users.manage" not in actor["permissions"]:
        raise HTTPException(status_code=403, detail="当前角色没有会员管理权限")
    if actor["id"] == user_id and (payload.role == "MEMBER" or payload.status == "SUSPENDED"):
        raise HTTPException(status_code=422, detail="不能移除或停用自己的管理员权限")
    user = store.update_user_access(user_id, payload.role, payload.status)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


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
def dashboard_overview(account_id: str | None = None, _: tuple[dict, str] = Depends(require_permission("dashboard.view"))) -> dict:
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


@app.post("/api/v1/control/auto-trading")
def auto_trading(payload: AutoTradingControl, _: dict | None = Depends(require_trade_control)) -> dict:
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
