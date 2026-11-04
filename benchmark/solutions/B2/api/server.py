"""The shop's HTTP API: GET /products."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer

from shop import catalog


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/products":
            products = [dict(p, price="$%d.%02d" % (p["price_cents"] // 100, p["price_cents"] % 100))
                        for p in catalog.all_products()]
            self.send_json(200, products)
        elif self.path.startswith("/products/") and self.path[len("/products/"):].isdigit():
            product = catalog.get(int(self.path[len("/products/"):]))
            if product is None:
                self.send_json(404, {"error": "not found"})
            else:
                p = product
                self.send_json(200, dict(p, price="$%d.%02d" % (p["price_cents"] // 100, p["price_cents"] % 100)))
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


class Server(HTTPServer):
    def server_bind(self):
        # HTTPServer looks the host name up on every start, which a local server doesn't need.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def make_server(port=0):
    return Server(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    make_server(8000).serve_forever()
