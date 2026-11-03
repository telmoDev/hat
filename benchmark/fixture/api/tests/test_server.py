import json
import threading
import unittest
import urllib.request

import server


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.httpd = server.make_server()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_products(self):
        with urllib.request.urlopen(self.base + "/products") as r:
            body = json.loads(r.read())
        self.assertEqual([p["name"] for p in body], ["Pen", "Notebook", "Bag"])
        self.assertEqual(body[0]["price"], "$1.50")
