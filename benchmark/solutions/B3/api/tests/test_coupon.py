import unittest

from shop.cart import Cart


class CouponTest(unittest.TestCase):
    def test_coupon_is_taken_off_once_after_the_bulk_discount(self):
        cart = Cart()
        cart.add(1, 10)
        self.assertEqual(cart.total("SAVE5"), 850)
