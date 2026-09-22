"""门面 API：把存储、目录、来源、计算、发布组装成一个研究组使用的工作空间。"""

from __future__ import annotations

import os

from . import publishing, registry, sources
from .engine import Engine, RunConfig, run_diff
from .store import EventStore


class Workspace:
    """一个研究工作空间对应一个 sqlite 数据库文件。"""

    def __init__(self, path: str = ":memory:"):
        self.store = EventStore(path)
        registry.bootstrap(self.store)
        self.engine = Engine(self.store)

    # —— 目录 ——

    def countries(self):
        return registry.countries(self.store)

    def region_mapping(self):
        return registry.region_mapping(self.store)

    def vocab(self, name):
        return registry.vocab(self.store, name)

    # —— 来源与导入 ——

    def register_source(self, source_id, kind, title, **kwargs):
        return sources.register_source(self.store, source_id, kind, title, **kwargs)

    def import_observation(self, source_id, obs):
        return sources.import_observation(self.store, source_id, obs)

    def resolve_cell(self, **kwargs):
        return sources.resolve_cell(self.store, **kwargs)

    def adjudicate(self, natural_key, winner_source_id, rationale, adjudicator):
        return sources.adjudicate(self.store, natural_key, winner_source_id,
                                  rationale, adjudicator)

    def retract_paper(self, source_id, reason):
        return sources.retract_paper(self.store, source_id, reason)

    def withdraw_risk_param(self, risk_id, reason, paper_ref=None):
        return registry.withdraw_risk_param(self.store, risk_id, reason, paper_ref)

    def flags(self, **kwargs):
        return self.store.flags(**kwargs)

    # —— 计算 ——

    def run(self, config: RunConfig | None = None, **config_kwargs):
        return self.engine.run(config or RunConfig(**config_kwargs))

    def rerun_for(self, parent_run_id: str, *, rationale: str,
                  country_codes=None, formula_version=None):
        """以父运行同样的配置在最新证据上再跑一次，只重算受影响分支。"""
        parent = self.store.get_run(parent_run_id)
        if parent is None:
            raise KeyError(parent_run_id)
        m = parent["manifest"]
        cfg = RunConfig(
            rationale=rationale,
            formula_id=m["formula"]["formula_id"],
            formula_version=formula_version or m["formula"]["version"],
            years=tuple(m["years"]),
            country_codes=tuple(m["countries"]) if country_codes is None
            else tuple(country_codes),
            parent_run_id=parent_run_id,
            trigger_seq=self.store.head_seq())
        result = self.engine.run(cfg)
        result["diff_vs_parent"] = run_diff(self.store, parent_run_id,
                                            result["run_id"])
        return result

    def diff(self, old_run_id, new_run_id):
        return run_diff(self.store, old_run_id, new_run_id)

    def run_manifest(self, run_id):
        run = self.store.get_run(run_id)
        return run["manifest"] if run else None

    # —— 发布 ——

    def publish(self, run_id, title, **kwargs):
        return publishing.publish(self.store, run_id, title, **kwargs)

    def report(self, report_id):
        return publishing.report_view(self.store, report_id)

    def annotate_report(self, report_id):
        return publishing.annotate_impacts(self.store, report_id)

    def supersede(self, old_report_id, new_report_id):
        return publishing.supersede(self.store, old_report_id, new_report_id)

    def verify_report(self, report_id):
        return publishing.verify_report(self.store, report_id)

    def explain(self, node_hash):
        return publishing.explain_number(self.store, node_hash)

    # —— 复现 ——

    def reproduce_run(self, run_id):
        """按运行记录的 cutoff 与配置原样重放；run_id 必须与历史一致。

        为保证逐位复现，重放配置（含 rationale、trigger_seq、parent 链接）完全
        取自历史清单，不掺入任何新字段——清单哈希即 run_id。
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        m = run["manifest"]
        cfg = RunConfig(
            rationale=m["rationale"],
            formula_id=m["formula"]["formula_id"],
            formula_version=m["formula"]["version"],
            years=tuple(m["years"]),
            country_codes=tuple(m["countries"]),
            parent_run_id=m["parent_run_id"],
            trigger_seq=m["trigger_seq"],
            notes=m.get("notes", {}))
        result = self.engine.run(cfg, cutoff_seq=m["cutoff_seq"])
        return {"requested_run_id": run_id, "replayed_run_id": result["run_id"],
                "identical": result["run_id"] == run_id,
                "cutoff_seq": m["cutoff_seq"]}

    def node(self, run_id, node_key):
        return self.store.node(run_id, node_key)


def open_workspace(path: str) -> Workspace:
    if path != ":memory:" and os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    return Workspace(path)
