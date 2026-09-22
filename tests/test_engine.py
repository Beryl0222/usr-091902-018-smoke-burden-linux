"""引擎测试：缺年标注、版本化公式、确定性、分支增量重算。"""

import math
import unittest

from burden import registry
from burden.engine import Engine, RunConfig, fill_series, levin_paf
from tests.helpers import build, run_once


class FillSeriesTest(unittest.TestCase):
    def test_interpolation_and_extrapolation_labels(self):
        obs = {2019: {"value": 0.2}, 2021: {"value": 0.4}}
        series = fill_series(obs, (2019, 2020, 2021))
        self.assertEqual(series[2019]["basis"], "observed")
        self.assertEqual(series[2020]["basis"], "estimated")
        self.assertEqual(series[2020]["method"], "linear_interpolation")
        self.assertAlmostEqual(series[2020]["value"], 0.3)
        self.assertEqual(series[2020]["anchor_years"], [2019, 2021])
        only = fill_series({2020: {"value": 0.3}}, (2019, 2020, 2021))
        self.assertEqual(only[2019]["method"], "nearest_extrapolation")
        self.assertAlmostEqual(only[2021]["value"], 0.3)
        self.assertEqual(only[2019]["anchor_years"], [2020])

    def test_no_observation_means_missing_never_fabricated(self):
        series = fill_series({}, (2019, 2020))
        self.assertTrue(all(p["basis"] == "missing" for p in series.values()))
        self.assertNotIn("value", series[2019])


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.ws = build()

    def test_run_deterministic_and_cached(self):
        r1 = run_once(self.ws)
        r2 = run_once(self.ws)
        self.assertEqual(r1["run_id"], r2["run_id"])
        self.assertGreater(r2["cache_hits"], 0)
        self.assertEqual(r2["cache_hits"], r2["node_count"])

    def test_missing_years_are_marked_estimated(self):
        r = run_once(self.ws)
        # 夹具只在 2020 有暴露观测：缺年生成估算节点
        for year, method in ((2019, "nearest_extrapolation"),
                             (2021, "nearest_extrapolation")):
            node = self.ws.node(r["run_id"], f"prev:CN:FMLE:ADULT:{year}")
            self.assertEqual(node["basis"], "estimated")
            self.assertEqual(node["method"]["name"], method)
        # 观测年不生成估算节点，PAF 节点直接标注 basis=observed
        paf_2020 = self.ws.node(r["run_id"], "paf:CN:IHD:ADULT:FMLE:2020")
        self.assertEqual(paf_2020["basis"], "observed")
        self.assertIsNone(paf_2020["method"])

    def test_paf_value_and_uncertainty(self):
        r = run_once(self.ws)
        paf = self.ws.node(r["run_id"], "paf:CN:IHD:ADULT:FMLE:2020")
        expected = levin_paf(0.30, 1.27)
        self.assertAlmostEqual(paf["value"], expected, places=10)
        self.assertLess(paf["unc_low"], paf["unc_high"])
        self.assertLessEqual(paf["unc_low"], paf["value"])
        self.assertGreaterEqual(paf["unc_high"], paf["value"])

    def test_formula_v2_changes_node_hashes_but_not_observed_branches(self):
        r1 = run_once(self.ws, formula_version=1)
        r2 = run_once(self.ws, formula_version=2)
        self.assertNotEqual(r1["run_id"], r2["run_id"])
        diff = self.ws.diff(r1["run_id"], r2["run_id"])
        # 暴露叶节点（观测）哈希不随公式版本变化
        self.assertTrue(any(k.startswith("leaf:claim") for k in diff["unchanged"]))
        self.assertTrue(all("paf:" in k or "attr:" in k or "global:" in k
                            or "region:" in k or "subregion:" in k
                            for k in diff["changed"]))

    def test_withdraw_param_recomputes_only_dependent_branch(self):
        r1 = run_once(self.ws)
        registry.withdraw_risk_param(self.ws.store, "RR_IHD_ADULT", "测试撤参")
        r2 = self.ws.rerun_for(r1["run_id"], rationale="撤回 IHD 参数")
        diff = r2["diff_vs_parent"]
        changed = set(diff["changed"]) | set(diff["removed"]) | set(diff["added"])
        # 所有变化节点都在 IHD 或聚合分支（聚合含 IHD 贡献）；
        # 其他疾病的国家级 attr 不变
        non_ihd_attr = [k for k in diff["unchanged"]
                        if k.startswith("attr:") and ":IHD:" not in k]
        self.assertTrue(non_ihd_attr)
        self.assertTrue(any(":IHD:" in k for k in changed))
        # 未受影响的观测叶子哈希保持一致
        self.assertTrue(any(k.startswith("leaf:claim") for k in diff["unchanged"]))

    def test_late_survey_changes_only_country_branch(self):
        r1 = run_once(self.ws)
        self.ws.register_source(
            "SURV-CN-NEW", "survey", "中国迟到调查",
            survey_design={"design": "cluster", "sample_size": 2000,
                           "weighting": "raking", "questions_version": "Qv4"})
        for sex in ("FMLE", "MLE"):
            for year in (2019, 2021):
                self.ws.import_observation("SURV-CN-NEW", {
                    "country_code": "CN", "year": year, "sex_id": sex,
                    "band_id": "ADULT", "indicator_id": "SHS_PREV",
                    "value": 0.18, "unc_low": 0.15, "unc_high": 0.21,
                    "sample_size": 2000})
        r2 = self.ws.rerun_for(r1["run_id"], rationale="补入中国迟到调查")
        diff = r2["diff_vs_parent"]
        changed_country_cells = {k.split(":")[1] for k in diff["changed"]
                                 if k.startswith(("prev:", "paf:", "attr:"))}
        self.assertTrue(changed_country_cells.issubset({"CN"}))
        # US 的国家级节点全部不变
        us_keys = [k for k in diff["unchanged"] if ":US:" in k]
        self.assertTrue(us_keys)

    def test_reproduce_is_bit_identical(self):
        r1 = run_once(self.ws)
        registry.withdraw_risk_param(self.ws.store, "RR_LUNGCA_ADULT", "后来撤参")
        repro = self.ws.reproduce_run(r1["run_id"])
        self.assertTrue(repro["identical"])

    def test_monte_carlo_is_reproducible_and_finite(self):
        from burden.engine import paf_with_uncertainty
        a = paf_with_uncertainty(0.3, 0.27, 0.33, 1.27, 1.10, 1.27 ** 2 / 1.10, 2)
        b = paf_with_uncertainty(0.3, 0.27, 0.33, 1.27, 1.10, 1.27 ** 2 / 1.10, 2)
        self.assertEqual(a, b)
        self.assertTrue(all(math.isfinite(x) for x in a))


if __name__ == "__main__":
    unittest.main()
