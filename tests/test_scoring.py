"""Sample numbers come from docs/02 (recomputed from the formulas, not the original draft)."""
import math
import unittest
from datetime import datetime

from domain import scoring
from domain.clock import VN_TZ

# docs/02: five videos of run_20261028T001700Z — (views, avg, likes, comments, age_h)
FIVE = {
    "vid001": (150_000, 5_000, 9_200, 410, 5.2867),
    "vid002": (120_000, 4_000, 6_800, 350, 8.8),
    "vid003": (8_000, 10_000, 310, 25, 36.3),
    "vid004": (95_000, 3_000, 6_100, 380, 16.3),
    "vid005": (2_000_000, 1_800_000, 85_000, 4_200, 30.0),
}
EXPECTED_VIRAL = {"vid001": 27.49, "vid002": 21.20, "vid003": 0.08, "vid004": 17.39, "vid005": 0.25}
EXPECTED_Z = {"vid001": 0.695, "vid002": 0.695, "vid003": -1.104, "vid004": 0.798, "vid005": -1.085}


class CohortTest(unittest.TestCase):
    def setUp(self):
        self.ratios = {k: scoring.performance_ratio(v[0], v[1]) for k, v in FIVE.items()}
        self.mu, self.sigma = scoring.cohort_mu_sigma(list(self.ratios.values()))
        self.m = scoring.median_raw_engagement(
            [(v[0], v[2], v[3]) for v in FIVE.values()], 1.5, 3.0
        )

    def test_mu_sigma(self):
        self.assertAlmostEqual(self.mu, 18.7156, places=3)
        self.assertAlmostEqual(self.sigma, 16.2272, places=3)

    def test_median_engagement_prior(self):
        self.assertAlmostEqual(self.m, 0.0938, places=4)

    def test_z_scores(self):
        for k, expected in EXPECTED_Z.items():
            z = scoring.z_score(self.ratios[k], self.mu, self.sigma)
            self.assertAlmostEqual(z, expected, places=2, msg=k)

    def test_viral_scores(self):
        for k, (views, _, likes, comments, age) in FIVE.items():
            eng = scoring.engagement(views, likes, comments, self.m, 1000, 1.5, 3.0)
            decay = scoring.time_decay(age, 0.05)
            viral = scoring.viral_score(views, eng, self.ratios[k], decay)
            self.assertAlmostEqual(viral, EXPECTED_VIRAL[k], delta=0.02, msg=k)

    def test_vid001_breakdown(self):
        views, _, likes, comments, age = FIVE["vid001"]
        eng = scoring.engagement(views, likes, comments, self.m, 1000, 1.5, 3.0)
        self.assertAlmostEqual(eng, 0.1002, places=4)
        self.assertAlmostEqual(scoring.time_decay(age, 0.05), 0.7677, places=3)

    def test_small_cohort_relaxes_theta(self):
        self.assertEqual(scoring.choose_z_threshold(5, 1.5, 0.5, 20), 0.5)
        self.assertEqual(scoring.choose_z_threshold(20, 1.5, 0.5, 20), 1.5)

    def test_theta_one_point_five_keeps_nothing_in_the_sample(self):
        zs = [scoring.z_score(r, self.mu, self.sigma) for r in self.ratios.values()]
        self.assertEqual([z for z in zs if z >= 1.5], [])
        self.assertEqual(sum(1 for z in zs if z >= 0.5), 3)


class NicheMatchTest(unittest.TestCase):
    def test_a_term_in_the_title_or_description_matches_case_insensitively(self):
        terms = ("国漫", "donghua")
        self.assertTrue(scoring.niche_match("3D国漫 第1集", "", terms))
        self.assertTrue(scoring.niche_match("EP12", "Best DONGHUA of the week", terms))
        self.assertFalse(scoring.niche_match("旅行 vlog", "美食", terms))

    def test_a_search_tag_alone_proves_nothing(self):
        self.assertFalse(scoring.niche_match("x", "", ()))

    def test_empty_terms_never_match_everything(self):
        self.assertFalse(scoring.niche_match("x", "y", ("",)))


class FormulaEdgeTest(unittest.TestCase):
    def test_half_life(self):
        self.assertAlmostEqual(scoring.half_life_hours(0.05), 13.86, places=2)

    def test_no_spread_means_z_zero(self):
        self.assertEqual(scoring.z_score(5.0, 5.0, 0.0), 0.0)
        self.assertEqual(scoring.z_score(5.0, 5.0, None), 0.0)

    def test_single_value_sigma_none(self):
        mu, sigma = scoring.cohort_mu_sigma([3.0])
        self.assertEqual((mu, sigma), (3.0, None))
        self.assertEqual(scoring.cohort_mu_sigma([]), (None, None))

    def test_zero_views_engagement(self):
        self.assertEqual(scoring.raw_engagement(0, 5, 5, 1.5, 3.0), 0.0)
        # smoothing pulls a zero-view video to the prior
        self.assertAlmostEqual(scoring.engagement(0, 0, 0, 0.09, 1000, 1.5, 3.0), 0.09)

    def test_multiplicative_collapse(self):
        self.assertEqual(scoring.viral_score(1000, 0.0, 10.0, 0.9), 0.0)
        self.assertTrue(math.isfinite(scoring.viral_score(10**9, 0.1, 1e6, 1.0)))


class VelocityTest(unittest.TestCase):
    # docs/04 snapshots: 07:17:12 and 18:17:10 (giờ VN) → 10.9994 h → 23,637.6 views/h
    T1 = datetime(2026, 10, 28, 7, 17, 12, tzinfo=VN_TZ).timestamp()
    T2 = datetime(2026, 10, 28, 18, 17, 10, tzinfo=VN_TZ).timestamp()
    # the third point (29/10 07:17) is 13 h after T2: v3 = 190,000 / 13 = 14,615, a3 ≈ -694
    T3 = datetime(2026, 10, 29, 7, 17, 10, tzinfo=VN_TZ).timestamp()

    def test_docs_example(self):
        v2 = scoring.velocity(150_000, self.T1, 410_000, self.T2)
        v3 = scoring.velocity(410_000, self.T2, 600_000, self.T3)
        a3 = scoring.acceleration(v2, self.T2, v3, self.T3)
        self.assertAlmostEqual(v2, 23637.6, delta=0.1)
        self.assertAlmostEqual(v3, 14615.4, delta=0.1)
        self.assertAlmostEqual(a3, -693.9, delta=0.2)
        self.assertFalse(scoring.early_flag(v3, a3, 10_000.0))  # past the peak

    def test_early_flag_needs_high_velocity_and_positive_acceleration(self):
        self.assertTrue(scoring.early_flag(100.0, 5.0, 50.0))
        self.assertFalse(scoring.early_flag(100.0, -5.0, 50.0))  # past the peak
        self.assertFalse(scoring.early_flag(10.0, 5.0, 50.0))
        self.assertFalse(scoring.early_flag(None, None, 50.0))
        self.assertFalse(scoring.early_flag(100.0, 5.0, None))

    def test_non_positive_dt(self):
        self.assertIsNone(scoring.velocity(1, 10.0, 2, 10.0))
        self.assertIsNone(scoring.acceleration(1.0, 10.0, 2.0, 5.0))

    def test_ema(self):
        out = scoring.ema([150_000, 410_000, 600_000], 0.3)
        self.assertEqual(out[0], 150_000)
        self.assertAlmostEqual(out[1], 228_000)
        self.assertAlmostEqual(out[2], 339_600)


if __name__ == "__main__":
    unittest.main()
