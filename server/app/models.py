from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccountSnapshot(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    balance: float = 0
    equity: float = 0
    free_margin: float = 0
    daily_pnl: float = 0
    drawdown_pct: float = Field(default=0, ge=0)
    is_demo: bool = True


class QuoteSnapshot(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    spread: float = Field(ge=0)
    atr: float = Field(default=0, ge=0)

    @field_validator("ask")
    @classmethod
    def ask_not_zero(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ask must be positive")
        return value


class PositionSnapshot(BaseModel):
    side: Literal["LONG", "SHORT"]
    volume: float = Field(gt=0)
    open_price: float = Field(gt=0)
    stop_loss: float = Field(default=0, ge=0)
    take_profit: float = Field(default=0, ge=0)
    pnl: float = 0
    ticket: int = 0


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: str = Field(min_length=8, max_length=96)
    ea_instance_id: str = Field(min_length=1, max_length=64)
    timestamp: datetime = Field(default_factory=utc_now)
    account: AccountSnapshot
    quote: QuoteSnapshot
    indicators: dict[str, float] = Field(default_factory=dict)
    position: PositionSnapshot | None = None
    strategy_version: str = Field(default="genesis-mt5-0.1.0", max_length=64)


class Heartbeat(BaseModel):
    ea_instance_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    ea_version: str = Field(default="0.1.0", max_length=32)
    auto_trading_local: bool = False
    timestamp: datetime = Field(default_factory=utc_now)


class AIDecision(BaseModel):
    action: Literal["LONG", "SHORT", "HOLD", "CLOSE", "REDUCE"] = "HOLD"
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = Field(default="", max_length=1000)
    entry_price: float = Field(default=0, ge=0)
    stop_loss: float = Field(default=0, ge=0)
    take_profit: float = Field(default=0, ge=0)
    long_votes: int = Field(default=0, ge=0, le=100)
    neutral_votes: int = Field(default=0, ge=0, le=100)
    short_votes: int = Field(default=0, ge=0, le=100)


class TradePlan(BaseModel):
    plan_id: str
    request_id: str
    account_id: str
    symbol: str
    action: Literal["LONG", "SHORT", "HOLD", "CLOSE", "REDUCE"]
    confidence: float
    threshold: float
    status: Literal["ACTIONABLE", "OBSERVE", "REJECTED"]
    reason: str
    entry_price: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    risk_percent: float = 0.5
    max_slippage_points: int = 30
    long_votes: int = 0
    neutral_votes: int = 0
    short_votes: int = 0
    provider: str
    model: str
    issued_at: datetime
    expires_at: datetime
    signature: str
    auto_trading_enabled: bool = False
    expires_in_seconds: int = 0


class OrderEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=96)
    plan_id: str = Field(min_length=1, max_length=96)
    account_id: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=48)
    ticket: int = 0
    message: str = Field(default="", max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class AutoTradingControl(BaseModel):
    enabled: bool
    confirmation: str = ""


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(LoginRequest):
    name: str = Field(min_length=2, max_length=64)


class AdminUserUpdate(BaseModel):
    role: Literal["ADMIN", "MEMBER"] | None = None
    status: Literal["ACTIVE", "SUSPENDED"] | None = None
