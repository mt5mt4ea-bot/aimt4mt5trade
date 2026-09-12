from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .ai import AIAnalyzer
from .config import Settings
from .models import MarketSnapshot, TradePlan
from .store import Store


class DecisionService:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self.ai = AIAnalyzer(settings)
        self._lock = asyncio.Lock()

    async def create_plan(self, snapshot: MarketSnapshot) -> TradePlan:
        async with self._lock:
            existing = self.store.latest("plans", snapshot.account.account_id)
            if existing and existing.get("request_id") == snapshot.request_id:
                return TradePlan.model_validate(existing)
            decision = await self.ai.analyze(snapshot)
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=min(120, self.settings.analysis_interval_seconds))
            server_auto = self.store.get_setting("auto_trading", str(self.settings.auto_trading_enabled).lower()) == "true"
            price_valid = self._price_structure_valid(decision.action, decision.entry_price, decision.stop_loss, decision.take_profit)
            actionable = decision.action in {"LONG", "SHORT", "CLOSE", "REDUCE"} and decision.confidence >= self.settings.min_confidence and price_valid
            status = "ACTIONABLE" if actionable else "OBSERVE"
            plan_id = "plan_" + secrets.token_hex(8)
            signature_payload = {
                "plan_id": plan_id,
                "request_id": snapshot.request_id,
                "account_id": snapshot.account.account_id,
                "symbol": snapshot.quote.symbol,
                "action": decision.action,
                "confidence": round(decision.confidence, 6),
                "entry_price": decision.entry_price,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "expires_at": expires.isoformat(),
            }
            signature = hmac.new(self.settings.plan_signing_secret.encode(), json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
            plan = TradePlan(
                **signature_payload,
                threshold=self.settings.min_confidence,
                status=status,
                reason=decision.reason,
                risk_percent=0.5,
                max_slippage_points=30,
                long_votes=decision.long_votes,
                neutral_votes=decision.neutral_votes,
                short_votes=decision.short_votes,
                provider=self.settings.ai_provider,
                model=self.settings.ai_model,
                issued_at=now,
                signature=signature,
                auto_trading_enabled=bool(server_auto and actionable),
                expires_in_seconds=max(0, int((expires-now).total_seconds())),
            )
            self.store.save_plan(json.loads(plan.model_dump_json()))
            return plan

    @staticmethod
    def _price_structure_valid(action: str, entry: float, stop: float, take: float) -> bool:
        if action == "LONG":
            return 0 < stop < entry < take
        if action == "SHORT":
            return 0 < take < entry < stop
        return action in {"HOLD", "CLOSE", "REDUCE"}

