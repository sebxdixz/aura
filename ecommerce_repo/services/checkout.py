from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckoutInput:
    cart_id: str
    coupon_code: str | None
    payment_token: str


def validate_coupon(coupon_code: str | None) -> bool:
    if coupon_code is None:
        return True
    normalized = coupon_code.strip().upper()
    if not normalized:
        return False
    if len(normalized) > 24:
        return False
    return normalized.isalnum()


def process_checkout(payload: CheckoutInput) -> dict:
    if not payload.cart_id:
        raise ValueError("missing cart id")
    if not validate_coupon(payload.coupon_code):
        raise ValueError("invalid coupon format")
    if payload.payment_token.startswith("tok_fail_"):
        raise RuntimeError("payment gateway timeout")
    return {"status": "ok", "cart_id": payload.cart_id}

