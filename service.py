"""二手烟负担证据计算服务。

除原有 ``/health`` 健康检查外，提供只追加证据链的 JSON API：

读取：GET  /api/catalog/countries | /api/vocab?name=diseases
      GET  /api/resolve?indicator_id&country_code&year&sex_id&band_id
      GET  /api/runs | /api/runs/{id} | /api/nodes/{run_id}/{node_key}
      GET  /api/explain/{node_hash} | /api/lineage?node_hash=
      GET  /api/reports | /api/reports/{id} | /api/reports/{id}/verify
      GET  /api/flags
写入：POST /api/sources | /api/observations | /api/adjudications
      POST /api/retractions/paper | /api/risk-params/withdraw
      POST /api/runs | /api/reports
      POST /api/reports/{id}/annotate | /api/reproduce/{run_id}

数据库路径由环境变量 ``SMOKE_BURDEN_DB`` 指定，默认 ``data/burden.sqlite3``。
"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from burden.api import Workspace, open_workspace
from burden.engine import RunConfig

SERVICE_ID = "smoke-burden"
SERVICE_NAME = "二手烟负担证据计算"
DEFAULT_DB = os.environ.get("SMOKE_BURDEN_DB", "data/burden.sqlite3")


def health_payload():
    """返回稳定的服务身份信息。"""
    return {"status": "ok", "service": SERVICE_ID, "name": SERVICE_NAME}


class Handler(BaseHTTPRequestHandler):
    """提供健康检查与证据链 JSON API。

    ``workspace`` 可通过类属性注入（测试用内存库）；否则按 ``db_path`` 惰性打开
    持久化工作空间。
    """

    workspace: Workspace | None = None
    db_path: str = DEFAULT_DB

    def ws(self) -> Workspace:
        if Handler.workspace is None:
            Handler.workspace = open_workspace(Handler.db_path)
        return Handler.workspace

    # —— 基础 ——

    def _send(self, payload, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str):
        self._send({"error": code, "message": message}, status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        try:
            if path == "/health":
                self._send(health_payload())
            elif path == "/api/catalog/countries":
                self._handle_countries()
            elif path == "/api/vocab":
                self._send({"rows": self.ws().vocab(query["name"][0])})
            elif path == "/api/resolve":
                self._handle_resolve(query)
            elif path == "/api/runs":
                self._send({"runs": self.ws().store.all_runs()})
            elif path.startswith("/api/runs/"):
                self._handle_run(path.split("/")[3])
            elif path.startswith("/api/nodes/"):
                self._handle_node(path.split("/")[3:])
            elif path.startswith("/api/explain/"):
                self._send(self.ws().explain(path.split("/")[3]))
            elif path == "/api/lineage":
                self._send({"lineage": self.ws().store.lineage(query["node_hash"][0])})
            elif path == "/api/reports":
                self._send({"reports": self.ws().store.list_reports()})
            elif path.startswith("/api/reports/"):
                self._handle_report(path.split("/")[3:])
            elif path == "/api/flags":
                self._send({"flags": self.ws().flags(
                    include_resolved=query.get("resolved", ["0"])[0] == "1")})
            else:
                self._error(404, "not_found", "未知路径")
        except KeyError as exc:
            self._error(404, "not_found", str(exc))
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(400, "bad_request", str(exc))
        except Exception as exc:  # noqa: BLE001 - API 边界统一兜底
            self._error(500, "internal_error", f"{type(exc).__name__}: {exc}")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/sources":
                b = self._body()
                for field_name in ("source_id", "kind", "title"):
                    if not b.get(field_name):
                        raise ValueError(f"缺少必填字段：{field_name}")
                self._send(self.ws().register_source(
                    b.pop("source_id"), b.pop("kind"), b.pop("title"), **b), 201)
            elif path == "/api/observations":
                b = self._body()
                if not b.get("source_id"):
                    raise ValueError("缺少必填字段：source_id")
                self._send(self.ws().import_observation(b.pop("source_id"), b), 201)
            elif path == "/api/adjudications":
                b = self._body()
                for field_name in ("natural_key", "winner_source_id",
                                   "rationale", "adjudicator"):
                    if field_name not in b:
                        raise ValueError(f"缺少必填字段：{field_name}")
                self._send(self.ws().adjudicate(
                    b["natural_key"], b["winner_source_id"],
                    b["rationale"], b["adjudicator"]), 201)
            elif path == "/api/retractions/paper":
                b = self._body()
                self._send(self.ws().retract_paper(b["source_id"], b["reason"]), 201)
            elif path == "/api/risk-params/withdraw":
                b = self._body()
                seq = self.ws().withdraw_risk_param(b["risk_id"], b["reason"],
                                                    b.get("paper_ref"))
                self._send({"status": "withdrawn", "risk_id": b["risk_id"],
                            "seq": seq}, 201)
            elif path == "/api/runs":
                b = self._body()
                if b.get("parent_run_id"):
                    self._send(self.ws().rerun_for(
                        b["parent_run_id"], rationale=b.get("rationale", "增量再计算"),
                        country_codes=b.get("country_codes"),
                        formula_version=b.get("formula_version")), 201)
                else:
                    cfg = RunConfig(
                        rationale=b.get("rationale", "通过 API 触发的计算"),
                        formula_version=b.get("formula_version", 1),
                        years=tuple(b.get("years", [2019, 2020, 2021])),
                        country_codes=(tuple(b["country_codes"])
                                       if b.get("country_codes") else None))
                    self._send(self.ws().run(cfg), 201)
            elif path == "/api/reports":
                b = self._body()
                self._send(self.ws().publish(
                    b["run_id"], b["title"], min_sample=b.get("min_sample", 50)), 201)
            elif path.endswith("/annotate") and path.startswith("/api/reports/"):
                report_id = path.split("/")[3]
                self._send(self.ws().annotate_report(report_id), 201)
            elif path.startswith("/api/reproduce/"):
                self._send(self.ws().reproduce_run(path.split("/")[3]), 201)
            else:
                self._error(404, "not_found", "未知路径")
        except KeyError as exc:
            self._error(404, "not_found", str(exc))
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(400, "bad_request", str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, "internal_error", f"{type(exc).__name__}: {exc}")

    # —— 资源处理 ——

    def _handle_countries(self):
        countries = self.ws().countries()
        self._send({"count": len(countries),
                    "countries": sorted(countries.values(),
                                        key=lambda c: c["code"])})

    def _handle_resolve(self, query):
        args = {k: query[k][0] for k in
                ("indicator_id", "country_code", "sex_id", "band_id")}
        args["year"] = int(query["year"][0])
        self._send(self.ws().resolve_cell(**args))

    def _handle_run(self, run_id):
        run = self.ws().store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        self._send(run)

    def _handle_node(self, parts):
        run_id, node_key = parts[0], "/".join(parts[1:])
        node = self.ws().node(run_id, node_key)
        if node is None:
            raise KeyError(node_key)
        self._send(node)

    def _handle_report(self, parts):
        report_id = parts[0]
        if len(parts) == 1:
            self._send(self.ws().report(report_id))
        elif parts[1] == "verify":
            self._send(self.ws().verify_report(report_id))
        else:
            self._error(404, "not_found", "未知路径")

    def log_message(self, *_args):
        return


def main():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        assert health_payload()["service"] == SERVICE_ID
        ws = Workspace(":memory:")
        assert len(ws.countries()) >= 200
        assert {v["band_id"] for v in ws.vocab("age_bands")} >= {
            "INF", "TOD", "CHILD", "ADO", "ADULT"}
        print(f"基础检查通过（{len(ws.countries())} 个国家/地区）")
        return
    Handler.db_path = args.db
    Handler.workspace = None
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
