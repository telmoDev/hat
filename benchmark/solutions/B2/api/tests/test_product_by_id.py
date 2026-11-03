import json
import threading
import unittest
import urllib.error
import urllib.request

import server


class ProductByIdTest(unittest.TestCase):
    def setUp(self):
        self.httpd = server.make_server()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_found_and_not_found(self):
        with urllib.request.urlopen(self.base + "/products/1") as r:
            self.assertEqual(json.loads(r.read())["name"], "Pen")
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(self.base + "/products/x")
        self.assertEqual(err.exception.code, 404)
