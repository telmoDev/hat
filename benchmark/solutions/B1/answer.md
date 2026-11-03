`Cart.total` takes the subtotal from `Cart.subtotal`, subtracts the coupon itself, then calls
`pricing.apply_discounts`, which adds the bulk discount and the coupon again, so a coupon is taken off twice.

```json
{"functions": ["cart.Cart.total", "cart.Cart.subtotal", "pricing.apply_discounts", "pricing.bulk_discount",
               "pricing.coupon_discount"],
 "totals": {"A": 300, "B": 1500, "C": 400},
 "coupon_applied_times": 2}
```
