from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

LegDict = Dict[str, object]


@dataclass
class MultiLegExecutionHelper:
    """Small helper that builds multi-leg payloads and falls back to legged orders."""

    execution_handler: object

    def build_payload(
        self,
        legs: List[LegDict],
        net_price_type: str = "debit",
        net_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict[str, object]:
        if net_price_type.lower() not in {"debit", "credit"}:
            raise ValueError("net_price_type must be 'debit' or 'credit'")

        normalized = [self._normalize_leg(leg, time_in_force) for leg in legs]
        return {
            "legs": normalized,
            "net_price_type": net_price_type.lower(),
            "net_price": net_price,
            "time_in_force": time_in_force,
        }

    def execute(
        self,
        legs: List[LegDict],
        net_price_type: str = "debit",
        net_price: Optional[float] = None,
        time_in_force: str = "day",
        transmit: bool = True,
    ) -> Dict[str, object]:
        payload = self.build_payload(legs, net_price_type=net_price_type, net_price=net_price, time_in_force=time_in_force)
        if not transmit:
            return payload

        submit = getattr(self.execution_handler, "submit_multileg_order", None)
        if callable(submit):
            return submit(payload)

        responses = []
        for leg in payload["legs"]:
            signal = self._leg_to_signal(leg)
            responses.append(self.execution_handler.execute_order(signal))
        return {"payload": payload, "responses": responses}

    @staticmethod
    def _normalize_leg(leg: LegDict, time_in_force: str) -> LegDict:
        required = {"action", "qty"}
        missing = required - leg.keys()
        if missing:
            raise ValueError(f"Leg is missing keys: {sorted(missing)}")
        normalized = {
            "action": str(leg["action"]).lower(),
            "qty": int(leg["qty"]),
            "asset_type": leg.get("asset_type", "option"),
            "time_in_force": leg.get("time_in_force", time_in_force),
            "order_type": leg.get("order_type", "limit"),
            "limit_price": leg.get("limit_price"),
        }
        normalized.update({k: v for k, v in leg.items() if k not in normalized})
        return normalized

    @staticmethod
    def _leg_to_signal(leg: LegDict) -> LegDict:
        signal = {
            "symbol": leg.get("symbol") or leg.get("underlying"),
            "action": leg["action"],
            "qty": leg["qty"],
            "type": leg.get("order_type", "limit"),
            "time_in_force": leg.get("time_in_force", "day"),
        }
        if leg.get("limit_price") is not None:
            signal["limit_price"] = leg["limit_price"]
        if leg.get("asset_type") == "option":
            signal.update(
                {
                    "asset_type": "option",
                    "option_type": leg.get("option_type"),
                    "strike": leg.get("strike"),
                    "expiration": leg.get("expiration"),
                }
            )
        return signal


__all__ = ["MultiLegExecutionHelper"]
