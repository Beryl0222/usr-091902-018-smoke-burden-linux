"""目录与版本化定义测试：240+ 地区、受控词表、风险参数撤回。"""

import unittest

from burden import registry
from burden.store import EventStore


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.store = EventStore(":memory:")
        registry.bootstrap(self.store)

    def test_over_200_countries_with_region_mapping(self):
        countries = registry.countries(self.store)
        self.assertGreaterEqual(len(countries), 200)
        mapping = registry.region_mapping(self.store)
        self.assertEqual(set(mapping), set(countries))
        for code, c in countries.items():
            self.assertTrue(c["un_subregion"])
            self.assertIn(c["who_region"],
                          {"AFRO", "AMRO", "EMRO", "EURO", "SEARO", "WPR", ""})

    def test_bootstrap_is_idempotent(self):
        seq_before = self.store.head_seq()
        registry.bootstrap(self.store)
        self.assertEqual(self.store.head_seq(), seq_before)

    def test_controlled_vocabularies(self):
        bands = {v["band_id"]: v for v in registry.vocab(self.store, "age_bands")}
        self.assertEqual([b for b, v in bands.items() if v["pediatric"]],
                         ["INF", "TOD", "CHILD", "ADO"])
        sexes = {v["sex_id"] for v in registry.vocab(self.store, "sexes")}
        self.assertEqual(sexes, {"FMLE", "MLE", "BTSX"})
        diseases = {v["disease_id"] for v in registry.vocab(self.store, "diseases")}
        self.assertIn("LRI", diseases)

    def test_indicator_versioning(self):
        ind = registry.indicator(self.store, "SHS_PREV")
        self.assertEqual(ind["version"], 1)
        self.assertTrue(ind["definition"])
        self.assertIn("ADULT", ind["eligible_bands"])

    def test_risk_param_withdrawn_is_hidden_after_seq_but_history_remains(self):
        self.assertTrue(registry.risk_param(self.store, "RR_IHD_ADULT"))
        seq = registry.withdraw_risk_param(self.store, "RR_IHD_ADULT", "测试撤回")
        self.assertIsNone(registry.risk_param(self.store, "RR_IHD_ADULT"))
        # cutoff 在撤回之前仍能看到旧参数
        self.assertTrue(registry.risk_param(self.store, "RR_IHD_ADULT",
                                            until_seq=seq - 1))
        # 历史事件未删除
        versions = self.store.aggregate_versions("risk_param:RR_IHD_ADULT")
        kinds = {e.event_type for e in versions}
        self.assertIn("risk_param_withdrawn", kinds)
        self.assertIn("risk_param_version", kinds)

    def test_formula_versions(self):
        v1 = registry.formula(self.store, "PAF_LEVIN", 1)
        v2 = registry.formula(self.store, "PAF_LEVIN", 2)
        self.assertIn("解析", v1["label"])
        self.assertIn("蒙特卡洛", v2["label"])


if __name__ == "__main__":
    unittest.main()
