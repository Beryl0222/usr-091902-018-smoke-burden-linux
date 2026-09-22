"""只追加存储测试：幂等、版本递增、乐观并发、cutoff 重放。"""

import unittest

from burden.store import EventStore, content_hash


class EventStoreTest(unittest.TestCase):
    def test_same_content_is_idempotent_and_same_hash(self):
        s = EventStore(":memory:")
        e1 = s.append("t", "agg:x", {"a": 1})
        e2 = s.append("t", "agg:x", {"a": 1})
        self.assertEqual(e1.seq, e2.seq)
        self.assertEqual(e1.payload_hash, e2.payload_hash)
        self.assertEqual(s.head_seq(), 1)

    def test_correction_appends_new_version_never_overwrites(self):
        s = EventStore(":memory:")
        e1 = s.append("t", "agg:x", {"v": 1})
        e2 = s.append("t", "agg:x", {"v": 2})
        self.assertEqual(e1.version, 1)
        self.assertEqual(e2.version, 2)
        versions = s.aggregate_versions("agg:x")
        self.assertEqual([x.payload["v"] for x in versions], [1, 2])
        self.assertEqual(s.get_event(e1.seq).payload["v"], 1)

    def test_expected_version_conflict(self):
        s = EventStore(":memory:")
        s.append("t", "agg:x", {"v": 1})  # 当前版本变为 1
        from burden.store import ConflictError
        with self.assertRaises(ConflictError):
            # 调用方拿着陈旧的版本号 0 去写 → 冲突
            s.append("t", "agg:x", {"v": 2}, expected_version=0)
        # 版本仍是 1，未发生写入
        self.assertEqual(len(s.aggregate_versions("agg:x")), 1)

    def test_until_seq_time_travel(self):
        s = EventStore(":memory:")
        s.append("t", "agg:x", {"v": 1})
        seq2 = s.append("t", "agg:y", {"v": 9}).seq
        s.append("t", "agg:z", {"v": 10})
        early = s.events(until_seq=seq2)
        self.assertEqual({e.aggregate for e in early}, {"agg:x", "agg:y"})

    def test_content_hash_deterministic(self):
        self.assertEqual(content_hash({"a": 1, "b": [1, 2]}),
                         content_hash({"b": [1, 2], "a": 1}))
        self.assertNotEqual(content_hash({"a": 1}), content_hash({"a": 2}))


if __name__ == "__main__":
    unittest.main()
