"""发布测试：拆分、最小样本与互补抑制、不可变报告、撤回标注、血缘解释。"""

import unittest

from burden import registry
from tests.helpers import build, run_once


class PublishingTest(unittest.TestCase):
    def setUp(self):
        self.ws = build()
        r = run_once(self.ws)
        self.run_id = r["run_id"]
        pub = self.ws.publish(self.run_id, "夹具报告", min_sample=50)
        self.report_id = pub["report_id"]

    def test_report_splits_by_sex_band_disease(self):
        view = self.ws.report(self.report_id)
        keys = {(c["disease_id"], c["sex"], c["age_band"])
                for c in view["cells"] if c["scope"] == "country"}
        self.assertIn(("IHD", "FMLE", "ADULT"), keys)
        self.assertIn(("IHD", "MLE", "ADULT"), keys)
        # 成人疾病不出现在儿童年龄段
        self.assertFalse(any(b == "INF" for *_, b in keys))

    def test_min_sample_primary_and_complementary_suppression(self):
        # 补一个男性极小样本国家单元（CV 2020）
        self.ws.register_source(
            "SURV-CV", "survey", "佛得角小调查",
            survey_design={"design": "cluster", "sample_size": 30,
                           "weighting": "w", "questions_version": "q"})
        for sex, n, v in (("MLE", 30, 0.3), ("FMLE", 800, 0.26)):
            self.ws.import_observation("SURV-CV", {
                "country_code": "CV", "year": 2020, "sex_id": sex,
                "band_id": "ADULT", "indicator_id": "SHS_PREV", "value": v,
                "unc_low": v - 0.03, "unc_high": v + 0.03, "sample_size": n})
            self.ws.import_observation("DEATHS", {
                "country_code": "CV", "year": 2020, "sex_id": sex,
                "band_id": "ADULT", "indicator_id": "DEATHS_BASE",
                "value": 600})
        r = run_once(self.ws, country_codes=("CN", "US", "CV"))
        pub = self.ws.publish(r["run_id"], "小样本报告", min_sample=50)
        view = self.ws.report(pub["report_id"])
        male = next(c for c in view["cells"]
                    if c.get("country_code") == "CV" and c["sex"] == "MLE")
        btsx = next(c for c in view["cells"]
                    if c.get("country_code") == "CV" and c["sex"] == "BTSX")
        self.assertEqual(male["status"], "suppressed")
        self.assertIn("small_sample", male["suppressed_reason"])
        self.assertIsNone(male["value"])
        self.assertEqual(btsx["status"], "suppressed")
        self.assertIn("complementary", btsx["suppressed_reason"])

    def test_report_is_immutable_after_withdrawal(self):
        before = self.ws.report(self.report_id)
        sample = next(c for c in before["cells"] if c["scope"] == "global_total")
        frozen_value = sample["value"]
        registry.withdraw_risk_param(self.ws.store, "RR_IHD_ADULT", "撤参测试")
        self.ws.annotate_report(self.report_id)
        after = self.ws.report(self.report_id)
        sample2 = next(c for c in after["cells"] if c["scope"] == "global_total")
        self.assertEqual(sample2["value"], frozen_value)
        self.assertTrue(self.ws.verify_report(self.report_id)["intact"])
        self.assertGreater(after["affected_cell_count"], 0)
        affected = next(c for c in after["cells"] if c["affected_by_retraction"])
        self.assertIn("撤回", affected["annotations"][0]["reason"])

    def test_explain_number_traces_inputs_and_formula(self):
        node = self.ws.node(self.run_id, "global:total:2020")
        explanation = self.ws.explain(node["node_hash"])
        self.assertEqual(explanation["basis"], "observed")
        self.assertTrue(explanation["inputs"]["claims"])
        self.assertTrue(explanation["inputs"]["risk_params"])
        formula = explanation["inputs"]["formulas"][0]
        self.assertEqual(formula["formula_id"], "PAF_LEVIN")
        self.assertEqual(formula["version"], 1)
        self.assertTrue(explanation["inputs"]["mapping_hashes"])

    def test_estimated_number_carries_method_in_report(self):
        # 夹具只有 2020 观测，2019 国家单元来自就近外推
        view = self.ws.report(self.report_id)
        cell_2019 = next(c for c in view["cells"]
                         if c.get("country_code") == "CN" and c["year"] == 2019
                         and c["sex"] == "FMLE")
        self.assertEqual(cell_2019["basis"], "estimated")
        self.assertEqual(cell_2019["method"]["name"], "nearest_extrapolation")


if __name__ == "__main__":
    unittest.main()
