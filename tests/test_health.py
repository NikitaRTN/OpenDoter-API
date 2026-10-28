from http.server import ThreadingHTTPServer
import json
import threading
import unittest
import urllib.error
import urllib.request
from server_modules.handler import Handler
from server_modules.app import APIHTTPServer


class HealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = APIHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%s" % cls.server.server_port
        cls.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_duplicate_port_is_rejected(self):
        with self.assertRaises(OSError):
            APIHTTPServer(("127.0.0.1", self.server.server_port), Handler)

    def test_root_and_health(self):
        for path in ("/", "/health", "/health?probe=1"):
            with self.subTest(path=path), self.client.open(self.base + path) as response:
                self.assertEqual(response.status, 200)
                payload = json.load(response)
                self.assertEqual(payload["service"], "OpenDoter API")
                self.assertEqual(payload["status"], "ok")

    def test_unknown_route_still_404(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(self.base + "/missing")
        self.assertEqual(error.exception.code, 404)

    def test_existing_status_route(self):
        with self.client.open(self.base + "/api/status/123") as response:
            self.assertEqual(json.load(response)["state"], "idle")


if __name__ == "__main__":
    unittest.main()
