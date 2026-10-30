import math
import unittest

from domain.dedup import cosine, greedy_clusters, novelty_score
from domain.llm_contract import LlmSchemaError, validate_llm
from tests.fakes import VECTORS, good_llm


class CosineTest(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cosine([1, 0], [-1, 0]), -1.0)
        self.assertAlmostEqual(cosine([2, 0], [1, 0]), 1.0)  # scale-free

    def test_zero_vector(self):
        self.assertEqual(cosine([0, 0], [1, 1]), 0.0)

    def test_docs_pair(self):
        self.assertAlmostEqual(cosine(VECTORS["vid001"], VECTORS["vid002"]), 0.81)


class ClusterTest(unittest.TestCase):
    def test_docs_example_vid001_leads_vid002_and_vid004_alone(self):
        ids = ["vid001", "vid002", "vid004"]
        clusters = greedy_clusters(
            [VECTORS[i] for i in ids], [27.49, 21.20, 17.39], 0.70, "run_x"
        )
        self.assertEqual([ids[c.leader] for c in clusters], ["vid001", "vid004"])
        self.assertEqual([c.duplicates_count for c in clusters], [1, 0])
        self.assertEqual([c.cluster_id for c in clusters], ["run_x_c0", "run_x_c1"])
        self.assertEqual(clusters[0].members, [1])

    def test_leader_is_highest_score_regardless_of_input_order(self):
        clusters = greedy_clusters([VECTORS["vid002"], VECTORS["vid001"]], [21.2, 27.49], 0.7, "r")
        self.assertEqual(clusters[0].leader, 1)

    def test_below_threshold_stays_separate(self):
        clusters = greedy_clusters([VECTORS["vid001"], VECTORS["vid002"]], [2, 1], 0.85, "r")
        self.assertEqual(len(clusters), 2)

    def test_no_chaining_through_a_member(self):
        # a~b and b~c but a!~c: c must not join a's cluster through b
        a, b, c = [1.0, 0.0], [math.cos(0.6), math.sin(0.6)], [math.cos(1.2), math.sin(1.2)]
        clusters = greedy_clusters([a, b, c], [3, 2, 1], 0.8, "r")
        self.assertEqual([cl.leader for cl in clusters], [0, 2])

    def test_empty(self):
        self.assertEqual(greedy_clusters([], [], 0.7, "r"), [])

    def test_novelty(self):
        self.assertEqual(novelty_score(None), 1.0)
        self.assertAlmostEqual(novelty_score(0.25), 0.75)
        self.assertEqual(novelty_score(1.2), 0.0)


class LlmContractTest(unittest.TestCase):
    def test_accepts_good_and_drops_extras(self):
        out = validate_llm({**good_llm(), "extra": 1})
        self.assertEqual(set(out), {"summary", "why_viral", "hook", "angles", "format", "risk"})

    def test_rejects(self):
        bad = [
            None, [], {},
            good_llm(summary=""), good_llm(hook=None), good_llm(why_viral=3),
            good_llm(angles=["a", "b"]), good_llm(angles=["a", "b", "c", "d"]),
            good_llm(angles=["a", "b", ""]), good_llm(angles="abc"),
            good_llm(format="podcast"), good_llm(risk="none"),
        ]
        for obj in bad:
            with self.subTest(obj=obj), self.assertRaises(LlmSchemaError):
                validate_llm(obj)

    def test_all_enum_values_pass(self):
        for fmt in ("long", "short", "compilation", "review"):
            validate_llm(good_llm(format=fmt))
        for risk in ("copyright", "reused", "kids", "sensitive"):
            validate_llm(good_llm(risk=risk))


if __name__ == "__main__":
    unittest.main()
