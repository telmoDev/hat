"""The products on sale. Prices are integer cents."""

PRODUCTS = {
    1: {"id": 1, "name": "Pen", "price_cents": 150},
    2: {"id": 2, "name": "Notebook", "price_cents": 400},
    3: {"id": 3, "name": "Bag", "price_cents": 2500},
}


def get(product_id):
    return PRODUCTS.get(product_id)


def all_products():
    return [PRODUCTS[k] for k in sorted(PRODUCTS)]


def format_price(cents):
    return "$%d.%02d" % (cents // 100, cents % 100)
