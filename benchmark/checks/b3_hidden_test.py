import unittest

from shop.cart import Cart


def cart(*items):
    c = Cart()
    for pid, qty in items:
        c.add(pid, qty)
    return c


class Hidden(unittest.TestCase):
    def test_O1_coupon_once(self):
        self.assertEqual(cart((3, 1)).total("SAVE5"), 2000)

    def test_O2_bulk_then_coupon(self):
        self.assertEqual(cart((1, 10)).total("SAVE5"), 850)

    def test_O2_bulk_without_coupon(self):
        self.assertEqual(cart((1, 10)).total(), 1350)

    def test_O3_never_negative(self):
        self.assertEqual(cart((1, 1)).total("SAVE5"), 0)
