from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from .config import Settings
from .models import AIDecision, MarketSnapshot

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a conservative market-analysis component, not an autonomous broker.
Analyze only the supplied snapshot. Return one JSON object and no markdown.
Required keys: action, confidence, reason, entry_price, stop_loss, take_profit,
long_votes, neutral_votes, short_votes.
action must be LONG, SHORT, HOLD, CLOSE, or REDUCE. confidence is 0..1.
Use HOLD when data is missing, contradictory, stale, or risk/reward is unclear.
For LONG require stop_loss < entry_price < take_profit; for SHORT require
take_profit < entry_price < stop_loss. Never claim guaranteed profit.
Example JSON: {"action":"HOLD","confidence":0.42,"reason":"insufficient alignment","entry_price":0,"stop_loss":0,"take_profit":0,"long_votes":4,"neutral_votes":15,"short_votes":5}
"""


class AIAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze(self, snapshot: MarketSnapshot) -> AIDecision:
        if not self.settings.ai_api_key:
            return self._safe_fallback(snapshot, "AI_API_KEY 未配置，系统保持观察模式。")
        payload = {
            "model": self.settings.ai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Analyze this market snapshot and output JSON:\n" + snapshot.model_dump_json(exclude_none=True)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 900,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.ai_api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.ai_api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("AI returned empty content")
            decision = AIDecision.model_validate(json.loads(content))
            return self._normalize(decision, snapshot)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("AI analysis failed safely: %s", exc)
            return self._safe_fallback(snapshot, f"AI 接口异常，已安全降级：{type(exc).__name__}")

    def _normalize(self, decision: AIDecision, snapshot: MarketSnapshot) -> AIDecision:
        price = (snapshot.quote.bid + snapshot.quote.ask) / 2
        decision.entry_price = decision.entry_price or price
        if decision.action == "LONG" and not (0 < decision.stop_loss < decision.entry_price < decision.take_profit):
            return self._safe_fallback(snapshot, "AI 多头价格结构无效，计划被拒绝。")
        if decision.action == "SHORT" and not (0 < decision.take_profit < decision.entry_price < decision.stop_loss):
            return self._safe_fallback(snapshot, "AI 空头价格结构无效，计划被拒绝。")
        if decision.action in {"LONG", "SHORT"}:
            max_distance = max(snapshot.quote.atr * 4, price * 0.02)
            if abs(decision.stop_loss - price) > max_distance or abs(decision.take_profit - price) > max_distance * 2:
                return self._safe_fallback(snapshot, "AI 价格距离超出服务端预检范围，计划被拒绝。")
        return decision

    def _safe_fallback(self, snapshot: MarketSnapshot, reason: str) -> AIDecision:
        indicators: dict[str, Any] = snapshot.indicators
        rsi = float(indicators.get("m15_rsi", 50))
        ema = float(indicators.get("m15_ema20", 0))
        long_votes = int(rsi < 40) + int(ema > 0 and snapshot.quote.bid > ema)
        short_votes = int(rsi > 60) + int(ema > 0 and snapshot.quote.bid < ema)
        return AIDecision(action="HOLD", confidence=0, reason=reason, long_votes=long_votes, neutral_votes=max(1, 5-long_votes-short_votes), short_votes=short_votes)

