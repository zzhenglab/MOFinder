"""Check pairwise selection and the contribution of repeated records."""
import unittest

import numpy as np
from mofinder.plotting.condition_coverage import (
    _select_pair, marker_colors, select_coordinates,
)


class ConditionCoverageTests(unittest.TestCase):
    def test_missingness_log_signs_and_record_multiplicity(self):
        records = np.array([
            [-78, 0.02, np.nan, np.nan],
            [-78, 0.02, 5, 2],
            [400, 7200, 10, 1],
            [100, 24, np.nan, 2],
            [100, 24.0001, 10, np.nan],
            [100, 0, 10, 1],
            [100, -1, 10, 1],
            [100, np.inf, 10, 1],
            [np.nan, 24, 10, 1],
        ])
        xy, multiplicities, counts = _select_pair(records, "time", "temperature")
        np.testing.assert_array_equal(xy, [[0.02, -78], [24, 100], [24.0001, 100], [7200, 400]])
        np.testing.assert_array_equal(multiplicities, [2, 1, 1, 1])
        self.assertEqual(counts["total_records"], 9)
        self.assertEqual(counts["finite_pair_records"], 7)
        self.assertEqual(counts["plotted_records"], 5)
        self.assertEqual(counts["omitted_missing_or_nonpositive"], 4)
        self.assertEqual(counts["distinct_coordinates"], 4)
        self.assertAlmostEqual(marker_colors("Positive", multiplicities)[0, 3], 1 - 0.76 ** 2)
        self.assertAlmostEqual(marker_colors("Negative", [1])[0, 3], 0.24)

    def test_full_ranges_empty_pairs_and_out_of_range_validation(self):
        records = np.array([[np.nan, np.nan, 0.7, 0.007], [np.nan, np.nan, 1e7, 1e6],
                            [np.nan, np.nan, 2001, 1], [np.nan, np.nan, 100, 0.049],
                            [np.nan, np.nan, 0, 1]])
        xy, counts = select_coordinates(records, "concentration", "ratio")
        np.testing.assert_array_equal(xy, [[0.7, 0.007], [100, 0.049], [2001, 1], [1e7, 1e6]])
        self.assertEqual(counts["plotted_records"], 4)
        xy, counts = select_coordinates(records, "temperature", "time")
        self.assertEqual(xy.shape, (0, 2))
        self.assertEqual(counts["finite_pair_records"], 0)
        with self.assertRaisesRegex(ValueError, "outside"):
            select_coordinates([[426, 1, 1, 1]], "time", "temperature")


if __name__ == "__main__":
    unittest.main()
