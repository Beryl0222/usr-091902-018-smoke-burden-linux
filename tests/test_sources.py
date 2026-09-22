"""来源与导入测试：合并、更正快照、冲突竞争、裁定、论文撤回。"""

import unittest

from burden import sources
from burden.store import EventStore
from tests.helpers import DESIGN

OBS = {"country_code": "CN", "year": 2020, "sex_id": "FMLE",
       "band_id": "ADULT", "indicator_id": "SHS_PREV", "value": 0.30,
       "unc_low": 0.27, "unc_high": 0.33, "sample_size": 1000}


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.s = EventStore(":memory:")
        sources.register_source(self.s, "S1", "survey", "调查一",
                                survey_design=DESIGN)
        sources.register_source(self.s, "S2", "survey", "调查二",
                                survey_design=DESIGN)
        sources.register_source(self.s, "L1", "literature", "文献一")

    def test_survey_requires_sampling_metadata(self):
        with self.assertRaises(ValueError):
            sources.register_source(self.s, "BAD", "survey", "缺元数据")

    def test_duplicate_import_merges(self):
        r1 = sources.import_observation(self.s, "S1", OBS)
        r2 = sources.import_observation(self.s, "S1", dict(OBS))
        self.assertEqual(r1["status"], "recorded")
        self.assertEqual(r2["status"], "merged")
        self.assertEqual(r1["seq"], r2["seq"])

    def test_correction_creates_new_snapshot_keeps_old(self):
        sources.import_observation(self.s, "S1", OBS)
        r2 = sources.import_observation(self.s, "S1", {**OBS, "value": 0.35})
        self.assertEqual(r2["status"], "corrected")
        self.assertNotEqual(r2["claim_hash"], r2["superseded_claim_hash"])
        cell = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")
        self.assertEqual(cell["state"], "observed")
        self.assertEqual(cell["claim"]["value"], 0.35)
        # 旧快照仍在
        versions = self.s.aggregate_versions(r2["claim_aggregate"])
        self.assertEqual([v.payload["value"] for v in versions], [0.30, 0.35])

    def test_distinct_sources_conflict_and_are_both_kept(self):
        sources.import_observation(self.s, "S1", OBS)
        r = sources.import_observation(self.s, "S2", {**OBS, "value": 0.41})
        self.assertTrue(r["conflict"])
        cell = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")
        self.assertEqual(cell["state"], "conflict")
        self.assertEqual({c["source_id"] for c in cell["competitors"]},
                         {"S1", "S2"})
        self.assertTrue(self.s.flags(include_resolved=False))

    def test_adjudication_picks_winner_but_keeps_competitors(self):
        sources.import_observation(self.s, "S1", OBS)
        sources.import_observation(self.s, "S2", {**OBS, "value": 0.41})
        sources.adjudicate(
            self.s,
            {k: OBS[k] for k in
             ("country_code", "year", "sex_id", "band_id", "indicator_id")},
            winner_source_id="S1", rationale="直接观测优先", adjudicator="甲")
        cell = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")
        self.assertEqual(cell["state"], "observed")
        self.assertEqual(cell["claim"]["source_id"], "S1")
        self.assertEqual(len(cell["competitors"]), 1)
        self.assertEqual(cell["competitors"][0]["source_id"], "S2")

    def test_correction_after_adjudication_reopens_conflict(self):
        sources.import_observation(self.s, "S1", OBS)
        sources.import_observation(self.s, "S2", {**OBS, "value": 0.41})
        nk = {k: OBS[k] for k in
              ("country_code", "year", "sex_id", "band_id", "indicator_id")}
        sources.adjudicate(self.s, nk, winner_source_id="S1",
                           rationale="r", adjudicator="甲")
        self.assertEqual(sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")["state"], "observed")
        # 胜方来源随后更正数值：旧裁定失效，不得静默采用新值
        sources.import_observation(self.s, "S1", {**OBS, "value": 0.50})
        cell = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")
        self.assertEqual(cell["state"], "conflict")
        self.assertTrue(cell.get("adjudication_stale"))

    def test_paper_retraction_excludes_claims_but_keeps_history(self):
        sources.import_observation(self.s, "L1", OBS)
        sources.retract_paper(self.s, "L1", "撤稿：数据造假")
        cell = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT")
        self.assertEqual(cell["state"], "retracted")
        # cutoff 在撤回之前仍是有效观测
        before = sources.resolve_cell(
            self.s, indicator_id="SHS_PREV", country_code="CN", year=2020,
            sex_id="FMLE", band_id="ADULT",
            until_seq=self.s.head_seq() - 1)
        self.assertEqual(before["state"], "observed")


if __name__ == "__main__":
    unittest.main()
