"""A shopping cart and its total."""
from . import catalog, pricing


class Cart:
    def __init__(self):
        self.items = {}

    def add(self, product_id, quantity=1):
        if catalog.get(product_id) is None:
            raise KeyError(product_id)
        self.items[product_id] = self.items.get(product_id, 0) + quantity

    def quantity(self):
        return sum(self.items.values())

    def subtotal(self):
        return sum(catalog.get(pid)["price_cents"] * qty for pid, qty in self.items.items())

    def total(self, coupon=None):
        return pricing.apply_discounts(self.subtotal(), self.quantity(), coupon)

    def summary(self, coupon=None):
        total = self.total(coupon)
        return "%d items, $%d.%02d" % (self.quantity(), total // 100, total % 100)
