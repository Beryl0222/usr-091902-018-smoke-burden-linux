"""端到端场景测试：第一版发布 → 迟到调查 + 参数撤回 → 分支重算 → 旧报告复现。"""

import unittest

from burden.scenario import run_scenario


class ScenarioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_scenario()
        cls.ws = cls.result["workspace"]

    def test_t0_dedup_correction_conflict_adjudication(self):
        self.assertTrue(self.result["dup_merged"])
        self.assertEqual(self.result["correction"]["status"], "corrected")
        self.assertTrue(self.result["correction"]["superseded_claim_hash"])
        self.assertEqual(self.result["adjudication"]["winner_source_id"], "SURV-US")

    def test_t1_first_release(self):
        r1 = self.result["run1"]
        self.assertEqual(len(set(n["node_hash"] for n in
                                 self.ws.store.nodes_of_run(r1["run_id"]))),
                         r1["node_count"])
        node = self.ws.node(r1["run_id"], "prev:IN:MLE:ADULT:2020")
        self.assertEqual(node["basis"], "estimated")
        self.assertEqual(node["method"]["name"], "linear_interpolation")

    def test_t1_min_sample_suppression(self):
        male = self.result["suppressed_cv_male"]
        btsx = self.result["suppressed_cv_btsx"]
        self.assertIn("small_sample", male["suppressed_reason"])
        self.assertIn("complementary", btsx["suppressed_reason"])
        self.assertIsNone(male["value"])

    def test_t3_only_dependent_branches_change(self):
        diff = self.result["diff"]
        changed = set(diff["changed"]) | set(diff["added"]) | set(diff["removed"])
        self.assertIn("attr:IN:IHD:ADULT:BTSX:2019", diff["unchanged"])

        # 以节点内容判定每个变化是否都可归因于「中国迟到调查」或「肺癌参数撤回」
        nodes1 = {n["node_key"]: n
                  for n in self.ws.store.nodes_of_run(self.result["run1"]["run_id"])}
        nodes2 = {n["node_key"]: n
                  for n in self.ws.store.nodes_of_run(self.result["run2"]["run_id"])}
        for key in changed:
            n = nodes1.get(key) or nodes2.get(key)
            head = key.split(":")[0]
            is_aggregate = head in ("global", "region", "subregion")
            is_disease_branch = ":LUNGCA:" in key
            is_china_branch = ":CN:" in key
            is_allowed_leaf = (
                head == "leaf" and (
                    n.get("leaf_kind") == "risk_param"
                    or (n.get("leaf_kind") == "claim"
                        and n.get("country_code") == "CN")))
            is_china_prev = key.startswith("prev:CN")
            self.assertTrue(
                is_aggregate or is_disease_branch or is_china_branch
                or is_allowed_leaf or is_china_prev,
                f"非依赖分支被意外重算：{key}")

    def test_t4_old_report_intact_annotated_and_reproducible(self):
        self.assertTrue(self.result["intact"]["intact"])
        self.assertGreater(self.result["impacts"]["new_annotations"], 0)
        self.assertTrue(any(":LUNGCA:" in a["cell_key"]
                            for a in self.result["impacts"]["affected"]))
        self.assertTrue(self.result["reproduce"]["identical"])
        # 撤回后新数字与旧数字不同
        self.assertNotEqual(self.result["total_2019_r1"],
                            self.result["total_2019_r2"])

    def test_t4_every_number_traceable(self):
        explained = self.result["explained"]
        self.assertTrue(explained["inputs"]["claims"])
        self.assertTrue(explained["inputs"]["risk_params"])
        self.assertEqual(explained["inputs"]["formulas"][0]["formula_id"],
                         "PAF_LEVIN")

    def test_reports_record_supersession_but_keep_both(self):
        reports = {r["report_id"]: r for r in self.ws.store.list_reports()}
        r1 = reports[self.result["report1"]]
        self.assertEqual(r1["superseded_by"], self.result["report2"])
        self.assertIsNotNone(self.ws.report(self.result["report1"]))
        self.assertIsNotNone(self.ws.report(self.result["report2"]))


if __name__ == "__main__":
    unittest.main()
