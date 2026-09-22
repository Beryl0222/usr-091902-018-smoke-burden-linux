"""HTTP JSON API 测试：在内存工作空间上打真实 HTTP 请求。"""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import service
from burden.api import Workspace


def request(base, method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class HttpApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service.Handler.workspace = Workspace(":memory:")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        service.Handler.workspace = None

    def test_01_health_and_catalog(self):
        status, body = request(self.base, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["service"], "smoke-burden")
        status, body = request(self.base, "GET", "/api/catalog/countries")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["count"], 200)

    def test_02_source_requires_design(self):
        status, body = request(self.base, "POST", "/api/sources",
                               {"source_id": "BAD", "kind": "survey",
                                "title": "无抽样设计"})
        self.assertEqual(status, 400)
        self.assertIn("抽样", body["message"])

    def test_03_full_workflow_over_http(self):
        b = self.base
        status, src = request(b, "POST", "/api/sources", {
            "source_id": "SURV", "kind": "survey", "title": "HTTP 调查",
            "survey_design": {"design": "cluster", "sample_size": 1000,
                              "weighting": "w", "questions_version": "q1"}})
        self.assertEqual(status, 201)
        request(b, "POST", "/api/sources",
                {"source_id": "DTH", "kind": "model", "title": "死亡模型"})

        obs = {"country_code": "CN", "year": 2020, "sex_id": "FMLE",
               "band_id": "ADULT", "indicator_id": "SHS_PREV", "value": 0.3,
               "unc_low": 0.27, "unc_high": 0.33, "sample_size": 1000}
        status, r1 = request(b, "POST", "/api/observations",
                             {"source_id": "SURV", **obs})
        self.assertEqual(status, 201)
        self.assertEqual(r1["status"], "recorded")
        status, r2 = request(b, "POST", "/api/observations",
                             {"source_id": "SURV", **obs})
        self.assertEqual(r2["status"], "merged")

        # 异源冲突 → 待裁定 → 裁定
        request(b, "POST", "/api/sources",
                {"source_id": "SURV2", "kind": "survey", "title": "调查2",
                 "survey_design": {"design": "cluster", "sample_size": 900,
                                   "weighting": "w", "questions_version": "q1"}})
        request(b, "POST", "/api/observations",
                {"source_id": "SURV2", **obs, "value": 0.41})
        status, cell = request(
            b, "GET", "/api/resolve?indicator_id=SHS_PREV&country_code=CN"
                      "&year=2020&sex_id=FMLE&band_id=ADULT")
        self.assertEqual(cell["state"], "conflict")
        status, adj = request(b, "POST", "/api/adjudications", {
            "natural_key": {"country_code": "CN", "year": 2020, "sex_id": "FMLE",
                            "band_id": "ADULT", "indicator_id": "SHS_PREV"},
            "winner_source_id": "SURV", "rationale": "HTTP 裁定",
            "adjudicator": "负责人"})
        self.assertEqual(status, 201)
        status, cell = request(
            b, "GET", "/api/resolve?indicator_id=SHS_PREV&country_code=CN"
                      "&year=2020&sex_id=FMLE&band_id=ADULT")
        self.assertEqual(cell["state"], "observed")
        self.assertEqual(cell["claim"]["source_id"], "SURV")

        # 男性暴露与两性别基线死亡，保证可计算
        for sex in ("FMLE", "MLE"):
            for year in (2019, 2020, 2021):
                request(b, "POST", "/api/observations", {
                    "source_id": "DTH", "country_code": "CN", "year": year,
                    "sex_id": sex, "band_id": "ADULT",
                    "indicator_id": "DEATHS_BASE", "value": 100000})
        request(b, "POST", "/api/observations", {
            "source_id": "SURV", "country_code": "CN", "year": 2020,
            "sex_id": "MLE", "band_id": "ADULT", "indicator_id": "SHS_PREV",
            "value": 0.34, "unc_low": 0.31, "unc_high": 0.37,
            "sample_size": 1000})

        status, run = request(b, "POST", "/api/runs",
                              {"rationale": "HTTP 运行",
                               "country_codes": ["CN"]})
        self.assertEqual(status, 201)
        run_id = run["run_id"]

        status, pub = request(b, "POST", "/api/reports",
                              {"run_id": run_id, "title": "HTTP 报告",
                               "min_sample": 50})
        self.assertEqual(status, 201)
        report_id = pub["report_id"]
        status, view = request(b, "GET", f"/api/reports/{report_id}")
        self.assertEqual(status, 200)
        self.assertGreater(len(view["cells"]), 0)

        # 撤参 → 增量运行 → 标注 → 核验
        status, wd = request(b, "POST", "/api/risk-params/withdraw",
                             {"risk_id": "RR_IHD_ADULT", "reason": "HTTP 撤参"})
        self.assertEqual(status, 201)
        status, rerun = request(b, "POST", "/api/runs",
                                {"parent_run_id": run_id,
                                 "rationale": "HTTP 增量"})
        self.assertEqual(status, 201)
        self.assertIn("diff_vs_parent", rerun)
        status, ann = request(b, "POST",
                              f"/api/reports/{report_id}/annotate")
        self.assertEqual(status, 201)
        self.assertGreater(ann["new_annotations"], 0)
        status, verify = request(b, "GET", f"/api/reports/{report_id}/verify")
        self.assertTrue(verify["intact"])
        status, repro = request(b, "POST", f"/api/reproduce/{run_id}")
        self.assertTrue(repro["identical"])

    def test_04_missing_and_bad_routes(self):
        status, _ = request(self.base, "GET", "/api/runs/run_nonexistent")
        self.assertEqual(status, 404)
        status, _ = request(self.base, "GET", "/nope")
        self.assertEqual(status, 404)
        status, _ = request(self.base, "POST", "/api/sources",
                            {"source_id": "X"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
