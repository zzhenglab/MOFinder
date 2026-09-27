"""Check embedding record identity and condition-only features."""
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from mofinder.plotting.split_embedding import (
    COORDINATE_DTYPE, PROVENANCE, build_features, generate_outputs, normalized_category,
    plot_embedding, validate_coordinates,
)


class SplitEmbeddingTests(unittest.TestCase):
    def test_coordinate_identity_requires_record_order_and_outcome(self):
        metadata = [("training", 1, "P"), ("holdout", 1, "N")]
        coordinates = np.array([("training", 1, "P", 0, 0), ("holdout", 1, "N", 0, 0)],
                               dtype=COORDINATE_DTYPE)
        validate_coordinates(coordinates, metadata)
        with self.assertRaises(ValueError):
            validate_coordinates(coordinates[::-1], metadata)
        coordinates[0]["label"] = "N"
        with self.assertRaises(ValueError):
            validate_coordinates(coordinates, metadata)
        coordinates[0]["label"] = "P"
        coordinates[0]["x"] = np.nan
        with self.assertRaises(ValueError):
            validate_coordinates(coordinates, metadata)

    def test_category_normalization_preserves_complete_combinations(self):
        self.assertEqual(normalized_category([" Zn ", "  Cu"]), "cu and zn")
        self.assertEqual(normalized_category("Zn AND Cu"), "cu and zn")
        self.assertEqual(normalized_category("  A\u00a0 B "), "a b")
        self.assertEqual(normalized_category(None), "<missing>")
        self.assertNotEqual(normalized_category("Zn"), normalized_category("Zn and Cu"))

    def test_outcomes_and_partitions_do_not_enter_feature_matrix(self):
        rows = [
            {"metal_precursor": "Zn", "organic_linker": "A", "modulator": None,
             "solvent": "water", "metal_concentration_mM": 10, "M_L_ratio": 1,
             "temperature_C": 20, "time_h": 24, "label": "P", "partition": "training"},
            {"metal_precursor": "Zn", "organic_linker": "A", "modulator": None,
             "solvent": "water", "metal_concentration_mM": None, "M_L_ratio": 1,
             "temperature_C": 20, "time_h": 24, "label": "N", "partition": "holdout"},
        ]
        features, audit = build_features(rows)
        relabeled = [dict(row, label="N" if row["label"] == "P" else "P",
                          partition="holdout" if row["partition"] == "training" else "training")
                     for row in rows]
        other, _ = build_features(relabeled)
        np.testing.assert_array_equal(features.toarray(), other.toarray())
        self.assertEqual(audit["numeric_imputation_medians"]["metal_concentration_mM"], 10)
        np.testing.assert_array_equal(features.toarray()[:, -4:], [[0, 0, 0, 0], [1, 0, 0, 0]])

    def test_subset_panels_preserve_coordinates_and_limits(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        coordinates = np.array([
            ("training", 1, "P", -2, 3), ("training", 2, "N", 4, 5),
            ("holdout", 1, "P", -6, -7), ("holdout", 2, "N", 8, -9),
        ], dtype=COORDINATE_DTYPE)
        fig = plot_embedding(coordinates)
        try:
            self.assertEqual(len(fig.axes), 5)
            self.assertEqual(len(fig.axes[0].collections[0].get_offsets()), 4)
            for ax, row in zip(fig.axes[1:], coordinates):
                np.testing.assert_array_equal(ax.collections[0].get_offsets(), [[row["x"], row["y"]]])
                self.assertEqual(ax.get_xlim(), fig.axes[0].get_xlim())
                self.assertEqual(ax.get_ylim(), fig.axes[0].get_ylim())
        finally:
            plt.close(fig)

    def test_refit_export_preserves_saved_coordinates(self):
        coordinates = np.array([
            ("training", 1, "P", -2, 3), ("training", 2, "N", 4, 5),
            ("holdout", 1, "P", -6, -7), ("holdout", 2, "N", 8, -9),
        ], dtype=COORDINATE_DTYPE)
        metadata = [(str(row["partition"]), int(row["row_index"]), str(row["label"]))
                    for row in coordinates]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "docs/dataset_analysis"
            saved = output / "data/tsne_coordinates.csv"
            saved.parent.mkdir(parents=True)
            saved.write_bytes(b"existing saved coordinates\n")
            (root / PROVENANCE).write_text("{}", encoding="utf-8")
            with patch("mofinder.plotting.split_embedding.read_inputs", return_value=([], metadata)):
                manifest = generate_outputs(coordinates, root, output, dpi=72, fit_audit={"checked": True})
            self.assertEqual(saved.read_bytes(), b"existing saved coordinates\n")
            self.assertTrue(manifest["embedding_refitted"])
            self.assertEqual(manifest["coordinate_source"], "data/tsne_coordinates_refit.csv")
            self.assertTrue((output / manifest["coordinate_source"]).is_file())


if __name__ == "__main__":
    unittest.main()
