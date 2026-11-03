"""Discounts: a bulk discount from 10 items, and coupons worth a fixed amount."""

BULK_MIN_QTY = 10
BULK_RATE_PERCENT = 10
COUPONS = {"SAVE5": 500}


def bulk_discount(subtotal, quantity):
    return subtotal * BULK_RATE_PERCENT // 100 if quantity >= BULK_MIN_QTY else 0


def coupon_discount(code):
    return COUPONS.get(code, 0)


def apply_discounts(subtotal, quantity, coupon=None):
    discount = bulk_discount(subtotal, quantity) + coupon_discount(coupon)
    return max(subtotal - discount, 0)
