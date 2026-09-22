"""服务契约：健康检查身份信息与 404 行为（保持最初脚手架的对外约定）。"""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import service


class ServiceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved = service.Handler.workspace
        service.Handler.workspace = None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.saved_workspace = saved

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        service.Handler.workspace = cls.saved_workspace

    def test_health_payload_has_stable_identity(self):
        self.assertEqual(service.health_payload(),
                         {"status": "ok", "service": service.SERVICE_ID,
                          "name": service.SERVICE_NAME})

    def test_health_endpoint_returns_json(self):
        with urlopen(f"{self.base_url}/health", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            self.assertEqual(json.load(response), service.health_payload())

    def test_unknown_route_is_not_exposed(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base_url}/unknown", timeout=2)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
