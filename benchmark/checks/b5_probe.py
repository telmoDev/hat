"""Prints what the api does for a fixed set of inputs, to compare before and after a refactor."""
import json
import threading
import urllib.request

import server
from shop import catalog
from shop.cart import Cart

out = {"prices": [catalog.format_price(c) for c in range(0, 200001, 7)], "summaries": []}
for items, coupon in (([(1, 2)], None), ([(3, 1)], "SAVE5"), ([(1, 10)], None), ([(1, 10), (2, 3)], "SAVE5"),
                      ([(2, 1)], "NOPE")):
    c = Cart()
    for pid, qty in items:
        c.add(pid, qty)
    out["summaries"].append(c.summary(coupon))
httpd = server.make_server()
threading.Thread(target=httpd.serve_forever, daemon=True).start()
with urllib.request.urlopen("http://127.0.0.1:%d/products" % httpd.server_address[1]) as r:
    out["products"] = json.loads(r.read())
httpd.shutdown()
httpd.server_close()
print(json.dumps(out, sort_keys=True))
