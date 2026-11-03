import json
import threading
import unittest
import urllib.error
import urllib.request

import server


class Hidden(unittest.TestCase):
    def setUp(self):
        self.httpd = server.make_server()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_O1_one_product(self):
        status, body = self.get("/products/2")
        listed = [p for p in self.get("/products")[1] if p["id"] == 2][0]
        self.assertEqual((status, body), (200, listed))

    def test_O2_unknown_id(self):
        self.assertEqual(self.get("/products/99"), (404, {"error": "not found"}))

    def test_O2_non_numeric_id(self):
        self.assertEqual(self.get("/products/abc"), (404, {"error": "not found"}))

    def test_O3_list_unchanged(self):
        status, body = self.get("/products")
        self.assertEqual(status, 200)
        self.assertEqual(body, [
            {"id": 1, "name": "Pen", "price_cents": 150, "price": "$1.50"},
            {"id": 2, "name": "Notebook", "price_cents": 400, "price": "$4.00"},
            {"id": 3, "name": "Bag", "price_cents": 2500, "price": "$25.00"}])
