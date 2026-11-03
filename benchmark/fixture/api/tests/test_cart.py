import unittest

from shop import catalog
from shop.cart import Cart


class CartTest(unittest.TestCase):
    def test_subtotal_and_total_without_discounts(self):
        cart = Cart()
        cart.add(1, 2)
        cart.add(2)
        self.assertEqual((cart.subtotal(), cart.total()), (700, 700))

    def test_bulk_discount_from_ten_items(self):
        cart = Cart()
        cart.add(1, 10)
        self.assertEqual(cart.total(), 1350)

    def test_summary(self):
        cart = Cart()
        cart.add(3)
        self.assertEqual(cart.summary(), "1 items, $25.00")

    def test_format_price(self):
        self.assertEqual(catalog.format_price(1350), "$13.50")

    def test_unknown_product(self):
        with self.assertRaises(KeyError):
            Cart().add(99)
