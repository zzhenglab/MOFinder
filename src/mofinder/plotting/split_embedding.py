"""Plot or fit a shared t-SNE embedding of synthesis conditions."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import unicodedata

import numpy as np

from .dataset_analysis import configure_style, sha256


CAPTION = (
    "Figure D10. t-SNE visualization of synthesis records. a, Combined dataset. "
    "b, Positive training records. c, Negative training records. d, Positive test records. "
    "e, Negative test records. All panels share coordinates and axis limits."
)
PROVENANCE = "docs/dataset_analysis/data/split_embedding_provenance.json"
COORDINATES = "docs/dataset_analysis/data/tsne_coordinates.csv"
CATEGORICAL = ("metal_precursor", "organic_linker", "modulator", "solvent")
NUMERIC = ("metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h")
COORDINATE_DTYPE = [
    ("partition", "U8"), ("row_index", "i8"), ("label", "U1"), ("x", "f8"), ("y", "f8")
]
SVD_SETTINGS = {"n_components": 50, "algorithm": "randomized", "n_iter": 5, "random_state": 42}
TSNE_SETTINGS = {
    "n_components": 2, "perplexity": 30, "early_exaggeration": 12,
    "learning_rate": "auto", "max_iter": 1000, "n_iter_without_progress": 300,
    "min_grad_norm": 1e-7, "metric": "euclidean", "init": "pca", "random_state": 42,
    "method": "barnes_hut", "angle": 0.5, "n_jobs": 4,
}


def normalized_category(value):
    """Normalize case, whitespace and member order within each category."""
    if value is None:
        return "<missing>"
    pieces = value if isinstance(value, list) else re.split(r"\s+and\s+", str(value), flags=re.IGNORECASE)
    pieces = [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(v))).strip().casefold()
              for v in pieces]
    pieces = [v for v in pieces if v]
    return " and ".join(sorted(pieces)) if pieces else "<missing>"


def read_inputs(project_root):
    """Read synthesis descriptors and keep outcomes in separate metadata."""
    root = Path(project_root)
    provenance = json.loads((root / PROVENANCE).read_text(encoding="utf-8"))
    rows, metadata = [], []
    for entry in provenance["repository_inputs"]:
        path = root / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError("Embedding input changed: " + entry["path"])
        labels = Counter()
        with path.open(encoding="utf-8-sig") as handle:
            for row_index, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                messages = json.loads(line)["messages"]
                conditions = [message["content"] for message in messages if message["role"] == "user"]
                answers = [message["content"].strip() for message in messages if message["role"] == "assistant"]
                if len(conditions) != 1 or len(answers) != 1 or answers[0] not in ("P", "N"):
                    raise ValueError("Expected one condition object and one P/N answer per record.")
                rows.append(json.loads(conditions[0]))
                metadata.append((entry["partition"], row_index, answers[0]))
                labels[answers[0]] += 1
        if dict(labels) != entry["outcomes"] or sum(labels.values()) != entry["records"]:
            raise ValueError("Embedding input counts differ from the expected dataset.")
    return rows, metadata


def validate_coordinates(coordinates, metadata):
    """Check every coordinate against its JSONL record, partition and outcome."""
    if len(coordinates) != len(metadata):
        raise ValueError("Coordinate and input record counts differ.")
    if not np.isfinite(coordinates["x"]).all() or not np.isfinite(coordinates["y"]).all():
        raise ValueError("All embedding coordinates must be finite.")
    actual = [(str(row["partition"]), int(row["row_index"]), str(row["label"])) for row in coordinates]
    if actual != metadata:
        raise ValueError("Coordinate order, row identities or outcomes differ from the input records.")


def load_embedding(project_root):
    """Load verified coordinates for the repository training and test records."""
    root = Path(project_root)
    provenance = json.loads((root / PROVENANCE).read_text(encoding="utf-8"))
    path = root / COORDINATES
    if sha256(path) != provenance["coordinates"]["sha256"]:
        raise ValueError("The embedding coordinate table changed.")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != [name for name, _ in COORDINATE_DTYPE]:
            raise ValueError("Unexpected coordinate table columns.")
        coordinates = np.array([
            (row["partition"], int(row["row_index"]), row["label"], float(row["x"]), float(row["y"]))
            for row in reader
        ], dtype=COORDINATE_DTYPE)
    _, metadata = read_inputs(root)
    validate_coordinates(coordinates, metadata)
    return coordinates


def build_features(rows):
    """Encode four categorical and four numeric condition descriptors."""
    from scipy import sparse
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    categorical = np.array([[normalized_category(row.get(key)) for key in CATEGORICAL]
                            for row in rows], dtype=object)
    numeric = np.array([[np.nan if row.get(key) is None else float(row[key]) for key in NUMERIC]
                        for row in rows], dtype=float)
    numeric[~np.isfinite(numeric)] = np.nan
    missing = np.isnan(numeric).astype(np.float32)
    encoder = OneHotEncoder(sparse_output=True, dtype=np.float32, handle_unknown="ignore")
    encoded = encoder.fit_transform(categorical)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    imputed = imputer.fit_transform(numeric)
    scaler = StandardScaler()
    standardized = scaler.fit_transform(imputed).astype(np.float32)
    features = sparse.hstack([encoded, sparse.csr_matrix(standardized), sparse.csr_matrix(missing)],
                             format="csr", dtype=np.float32)
    audit = {
        "categories_by_field": {key: len(value) for key, value in zip(CATEGORICAL, encoder.categories_)},
        "numeric_missing_counts": dict(zip(NUMERIC, missing.sum(axis=0).astype(int).tolist())),
        "numeric_imputation_medians": dict(zip(NUMERIC, imputer.statistics_.tolist())),
        "numeric_scaler_means": dict(zip(NUMERIC, scaler.mean_.tolist())),
        "numeric_scaler_scales": dict(zip(NUMERIC, scaler.scale_.tolist())),
        "descriptor_shape": list(features.shape), "descriptor_nonzero_entries": int(features.nnz),
    }
    return features, audit


def fit_embedding(project_root):
    """Fit all condition descriptors together; labels are used only for display."""
    import platform
    import scipy
    import sklearn
    from sklearn.decomposition import TruncatedSVD
    from sklearn.manifold import TSNE
    from threadpoolctl import threadpool_limits

    rows, metadata = read_inputs(project_root)
    features, audit = build_features(rows)
    svd = TruncatedSVD(**SVD_SETTINGS)
    tsne = TSNE(**TSNE_SETTINGS)
    with threadpool_limits(limits=4):
        reduced = svd.fit_transform(features)
        xy = tsne.fit_transform(reduced)
    coordinates = np.array([(*row, float(x), float(y)) for row, (x, y) in zip(metadata, xy)],
                           dtype=COORDINATE_DTYPE)
    validate_coordinates(coordinates, metadata)
    audit.update({
        "svd": {**SVD_SETTINGS, "explained_variance_ratio_sum": float(svd.explained_variance_ratio_.sum())},
        "tsne": {**TSNE_SETTINGS, "effective_learning_rate": float(tsne.learning_rate_),
                 "kl_divergence": float(tsne.kl_divergence_), "n_iter_completed_zero_based": int(tsne.n_iter_)},
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "scikit_learn": sklearn.__version__},
    })
    return coordinates, audit


def plot_embedding(coordinates):
    """Draw the overview and four subsets on a shared coordinate system."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    configure_style()
    minimum = np.array([coordinates["x"].min(), coordinates["y"].min()])
    maximum = np.array([coordinates["x"].max(), coordinates["y"].max()])
    center = (minimum + maximum) / 2
    span = float(np.max(maximum - minimum) * 1.06)
    xlim = (center[0] - span / 2, center[0] + span / 2)
    ylim = (center[1] - span / 2, center[1] + span / 2)
    width, height = 6, 3.9
    fig = plt.figure(figsize=(width, height))

    def axis_at(left, bottom, size, letter):
        ax = fig.add_axes([left / width, bottom / height, size / width, size / height])
        ax.set(xlim=xlim, ylim=ylim, aspect="equal", xticks=[], yticks=[])
        for spine in ax.spines.values():
            spine.set_color("#707070")
            spine.set_linewidth(0.5)
        ax.text(0, 1.045, letter, transform=ax.transAxes, fontsize=12, fontweight="bold")
        return ax

    overview = axis_at(0.38, 0.67, 2.66, "a")
    order = np.random.default_rng(42).permutation(len(coordinates))
    colors = np.where(coordinates["label"] == "P", "#285953", "#8D969E")[order]
    overview.scatter(coordinates["x"][order], coordinates["y"][order], c=colors,
                     s=1.4, alpha=0.65, linewidths=0, edgecolors="none")
    overview.set_title(f"All records\n(n = {len(coordinates):,})", fontsize=8, pad=6, linespacing=1.15)
    overview.set_xlabel("t-SNE 1", fontsize=8, labelpad=4)
    overview.set_ylabel("t-SNE 2", fontsize=8, labelpad=4)
    handles = [Line2D([], [], color="none", marker="o", markerfacecolor=color,
                      markeredgecolor="none", markersize=3.8, label=label)
               for color, label in [("#285953", "Positive"), ("#8D969E", "Negative")]]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(1.71 / width, 0.30 / height),
               frameon=False, ncol=2, borderaxespad=0, handletextpad=0.3, columnspacing=0.8)
    specs = [
        ("training", "P", "Train positive", 3.20, 2.20, "b"),
        ("training", "N", "Train negative", 4.64, 2.20, "c"),
        ("holdout", "P", "Test positive", 3.20, 0.50, "d"),
        ("holdout", "N", "Test negative", 4.64, 0.50, "e"),
    ]
    for partition, label, title, left, bottom, letter in specs:
        ax = axis_at(left, bottom, 1.30, letter)
        subset = coordinates[(coordinates["partition"] == partition) & (coordinates["label"] == label)]
        ax.scatter(subset["x"], subset["y"], s=2.4,
                   facecolors="#A2C4F1" if label == "P" else "#F2DAE7",
                   edgecolors="#A2C4F1" if label == "P" else "#D9AEC6",
                   linewidths=0 if label == "P" else 0.12, alpha=1)
        ax.set_title(f"{title}\n(n = {len(subset):,})", fontsize=8, pad=5, linespacing=1.15)
    return fig


def generate_outputs(coordinates, project_root, output_dir, dpi=600, fit_audit=None):
    """Save the figure and its reproducibility metadata."""
    import matplotlib.pyplot as plt

    root, output = Path(project_root), Path(output_dir)
    png = output / "figures/Figure_D10_training_test_tsne.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    _, metadata = read_inputs(root)
    validate_coordinates(coordinates, metadata)
    fig = plot_embedding(coordinates)
    fig.savefig(png, dpi=dpi)
    limits = {"x": list(fig.axes[0].get_xlim()), "y": list(fig.axes[0].get_ylim())}
    plt.close(fig)
    manifest = {
        "figure": "D10", "caption": CAPTION, "total_records": len(coordinates),
        "counts": {partition: {label: int(np.sum((coordinates["partition"] == partition)
                                                 & (coordinates["label"] == label))) for label in ("P", "N")}
                   for partition in ("training", "holdout")},
        "coordinate_source": "data/tsne_coordinates_refit.csv" if fit_audit is not None else COORDINATES,
        "embedding_refitted": fit_audit is not None,
        "dimensions_inches": [6, 3.9], "dpi": dpi, "limits_all_panels": limits,
        "png": png.relative_to(output).as_posix(), "png_sha256": sha256(png),
        "provenance_sha256": sha256(root / PROVENANCE),
    }
    if fit_audit is not None:
        coordinate_path = output / "data/tsne_coordinates_refit.csv"
        coordinate_path.parent.mkdir(parents=True, exist_ok=True)
        with coordinate_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([name for name, _ in COORDINATE_DTYPE])
            for row in coordinates:
                writer.writerow([row["partition"], row["row_index"], row["label"],
                                 f"{row['x']:.9g}", f"{row['y']:.9g}"])
        manifest["coordinates_sha256"] = sha256(coordinate_path)
        manifest["fit"] = fit_audit
    else:
        manifest["coordinates_sha256"] = sha256(root / COORDINATES)
    (output / "split_embedding_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("results/dataset_analysis"))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--refit", action="store_true", help="Fit descriptors, SVD and t-SNE again.")
    args = parser.parse_args(argv)
    if args.check_only:
        coordinates = load_embedding(args.project_root)
        print(f"Verified coordinates and dataset identities for {len(coordinates):,} records.")
        return
    if args.refit:
        coordinates, audit = fit_embedding(args.project_root)
    else:
        coordinates, audit = load_embedding(args.project_root), None
    output = args.output if args.output.is_absolute() else args.project_root / args.output
    generate_outputs(coordinates, args.project_root, output, fit_audit=audit)
    print(f"Saved Figure D10 for {len(coordinates):,} records.")


if __name__ == "__main__":
    main()
