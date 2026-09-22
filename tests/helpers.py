"""测试夹具：构建小型数据集，避免每个测试都跑全球场景。"""

from __future__ import annotations

from burden.api import Workspace

DESIGN = {"design": "stratified_cluster", "sample_size": 1000,
          "weighting": "post_stratification", "questions_version": "Qv3"}


def build() -> Workspace:
    """两个国家（CN/US）、仅成人 IHD 的最小可计算数据集，2020 为观测年。"""
    ws = Workspace(":memory:")
    ws.register_source("SURV", "survey", "夹具调查", survey_design=DESIGN)
    ws.register_source("DEATHS", "model", "夹具基线死亡模型")
    for cc in ("CN", "US"):
        for sex in ("FMLE", "MLE"):
            ws.import_observation("SURV", {
                "country_code": cc, "year": 2020, "sex_id": sex,
                "band_id": "ADULT", "indicator_id": "SHS_PREV", "value": 0.30,
                "unc_low": 0.27, "unc_high": 0.33, "sample_size": 1000})
            for year in (2019, 2020, 2021):
                ws.import_observation("DEATHS", {
                    "country_code": cc, "year": year, "sex_id": sex,
                    "band_id": "ADULT", "indicator_id": "DEATHS_BASE",
                    "value": 100_000})
    return ws


def run_once(ws: Workspace, **kwargs):
    from burden.engine import RunConfig
    kwargs.setdefault("rationale", "夹具运行")
    kwargs.setdefault("country_codes", ("CN", "US"))
    return ws.run(RunConfig(**kwargs))
