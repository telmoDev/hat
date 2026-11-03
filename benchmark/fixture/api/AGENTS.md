# api

A small shop backend: standard-library Python 3.8+, no dependencies.

- Layout: `shop/catalog.py` (products), `shop/pricing.py` (discounts), `shop/cart.py` (cart and totals),
  `server.py` (HTTP API on `http.server`), tests in `tests/`.
- Money is integer cents.
- Checks: `python3 -m unittest discover -s tests -t .` (run from this directory).
- Commits: Conventional Commits.
