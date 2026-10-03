"""Offline positive-class reliability metrics for complete saved predictions.

ECE uses fixed equal-width bins [lower, upper), with 1 included in the last bin.
No probabilities are fitted, clipped, imputed, or silently dropped. Optional DOI
bootstrap draws are shared across models and retain all records of sampled DOIs.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

DEFAULT_COLUMNS = ("mofinder_probability_P", "base_oss_probability_P", "gpt41_probability_P")
DEFAULT_CSV = Path(__file__).resolve().parents[3] / "benchmarks/reaction_holdout/calibration/predictions.csv"
DEFAULT_SEED = 20261002


def token_probability(logprob_P: float, logprob_N: float) -> float:
    """P probability conditional on two label tokens at the same output position.

    Inputs must be finite log probabilities (or logits), without token bias.
    Missing alternative tokens require separate treatment, not substitution here.
    """
    try:
        p, n = float(logprob_P), float(logprob_N)
    except (TypeError, ValueError) as exc:
        raise ValueError("Both P and N log probabilities must be finite numbers.") from exc
    if not math.isfinite(p) or not math.isfinite(n):
        raise ValueError("Both P and N log probabilities must be finite.")
    maximum = max(p, n)
    p, n = math.exp(p - maximum), math.exp(n - maximum)
    return p / (p + n)


def _arrays(labels, probabilities):
    y, p = np.asarray(labels, dtype=float), np.asarray(probabilities, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or y.shape != p.shape or not y.size:
        raise ValueError("Labels and probabilities must be nonempty, equal-length one-dimensional arrays.")
    if not np.isfinite(y).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Labels must contain only 0 and 1.")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Every probability must be finite and within [0, 1]; missing rows are not dropped.")
    return y, p


def _check_bins(bins):
    if isinstance(bins, bool) or not isinstance(bins, (int, np.integer)) or bins < 1:
        raise ValueError("bins must be a positive integer.")


def _bin_index(p, bins):
    return np.minimum(np.floor(p * bins).astype(int), bins - 1)


def calibration_metrics(labels, probabilities, *, bins: int = 10) -> dict:
    """Return record-weighted positive-class ECE, binary Brier, and accuracy.

    Accuracy uses P when p(P) >= 0.5, including exact ties. Brier is the binary
    convention mean((p-y)**2), not a sum over two classes.
    """
    _check_bins(bins)
    y, p = _arrays(labels, probabilities)
    index = _bin_index(p, bins)
    residual = np.bincount(index, weights=y-p, minlength=bins)
    return {"n": len(y), "accuracy": float(np.mean((p >= .5) == y)),
            "ece": float(np.abs(residual).sum() / len(y)),
            "brier": float(np.mean((p-y)**2))}


@dataclass
class PredictionData:
    labels: np.ndarray
    probabilities: dict[str, np.ndarray]
    dois: tuple[str, ...] | None


def load_predictions(path, *, probability_columns: Sequence[str] | None = None,
                     label_column: str = "y") -> PredictionData:
    """Read the shared-cohort wide CSV, or explicitly named model columns.

    Default wide input requires record_id, input_sha256, doi, y, and all three
    DEFAULT_COLUMNS. Existing holdout exports are supported by selecting prob_P
    and gold_label; example_index and canonicalized user_text provide identity.
    Duplicate IDs or condition hashes and incomplete model rows are rejected.
    """
    wide = probability_columns is None
    columns = tuple(DEFAULT_COLUMNS if wide else probability_columns)
    if not columns or len(set(columns)) != len(columns):
        raise ValueError("Choose at least one distinct probability column.")
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if not headers or len(set(headers)) != len(headers):
            raise ValueError("CSV must have distinct column names.")
        required = set(columns) | {label_column}
        if wide:
            required |= {"record_id", "input_sha256", "doi"}
        missing = required - set(headers)
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        id_column = "record_id" if "record_id" in headers else "example_index"
        if id_column not in headers:
            raise ValueError("CSV requires record_id or example_index.")
        if "input_sha256" not in headers and "user_text" not in headers:
            raise ValueError("CSV requires input_sha256 or user_text for duplicate-input checks.")
        ids, hashes, labels, dois = set(), set(), [], []
        values = {name: [] for name in columns}
        for row in reader:
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row at line {line}.")
            identity = row[id_column].strip()
            if not identity or identity in ids:
                raise ValueError(f"Missing or duplicate record ID at line {line}.")
            ids.add(identity)
            if "input_sha256" in headers:
                digest = row["input_sha256"].strip().lower()
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError(f"Invalid input_sha256 at line {line}.")
            else:
                try:
                    obj = json.loads(row["user_text"])
                    if not isinstance(obj, dict):
                        raise ValueError("Expected a reaction object.")
                    canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid user_text JSON at line {line}.") from exc
            if digest in hashes:
                raise ValueError(f"Duplicate input hash at line {line}.")
            hashes.add(digest)
            raw_label = row[label_column].strip()
            if raw_label not in {"0", "1", "N", "P"}:
                raise ValueError(f"Invalid binary label at line {line}: expected 0/1 or N/P.")
            labels.append(int(raw_label in {"1", "P"}))
            for name in columns:
                try:
                    value = float(row[name])
                except ValueError as exc:
                    raise ValueError(f"Missing or invalid {name} at line {line}.") from exc
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"Nonfinite or out-of-range {name} at line {line}.")
                values[name].append(value)
            if "doi" in headers:
                doi = row["doi"].strip()
                if not doi:
                    raise ValueError(f"Missing DOI at line {line}.")
                dois.append(doi)
    if not labels:
        raise ValueError("CSV contains no prediction records.")
    return PredictionData(np.asarray(labels), {k: np.asarray(v) for k, v in values.items()},
                          tuple(dois) if "doi" in headers else None)


def evaluate_predictions(labels, probabilities: Mapping[str, Sequence[float]], *,
                         bins: int = 10, dois: Sequence[str] | None = None,
                         bootstrap: int = 0, seed: int = DEFAULT_SEED) -> dict:
    """Evaluate complete paired model columns, optionally with DOI bootstrap CIs.

    Each replicate uniformly samples the original number of DOI groups with
    replacement. Every record of every selected group is included, with group
    multiplicity; metrics remain record-weighted. All models share the draws.
    Intervals are 2.5th/97.5th percentiles, conditional on fitted models/labels.
    """
    _check_bins(bins)
    if isinstance(bootstrap, bool) or not isinstance(bootstrap, (int, np.integer)) or bootstrap < 0:
        raise ValueError("bootstrap must be a nonnegative integer.")
    if not probabilities:
        raise ValueError("At least one probability column is required.")
    arrays = {name: _arrays(labels, p)[1] for name, p in probabilities.items()}
    y = np.asarray(labels, dtype=float)
    models = {name: calibration_metrics(y, p, bins=bins) for name, p in arrays.items()}
    result = {"n": len(y), "bins": int(bins), "definition": "positive-class ECE; binary Brier; P if p>=0.5",
              "models": models, "bootstrap_replicates": int(bootstrap)}
    if not bootstrap:
        return result
    if dois is None or len(dois) != len(y) or any(not isinstance(d, str) or not d.strip() for d in dois):
        raise ValueError("DOI bootstrap requires one nonempty DOI per record.")
    names, groups = np.unique(np.asarray(dois), return_inverse=True)
    n_groups = len(names)
    if n_groups < 2:
        raise ValueError("DOI bootstrap requires at least two DOI groups.")
    # Preaggregate sufficient statistics by DOI; resampling rows is unnecessary.
    width = 2 + bins
    aggregate = np.zeros((n_groups, 1 + len(arrays) * width))
    aggregate[:, 0] = np.bincount(groups, minlength=n_groups)
    for j, p in enumerate(arrays.values()):
        start = 1 + j * width
        aggregate[:, start] = np.bincount(groups, weights=(p >= .5) == y, minlength=n_groups)
        aggregate[:, start+1] = np.bincount(groups, weights=(p-y)**2, minlength=n_groups)
        np.add.at(aggregate[:, start+2:start+width], (groups, _bin_index(p, bins)), y-p)
    samples = np.empty((bootstrap, len(arrays), 3))
    rng = np.random.default_rng(seed)
    for i in range(bootstrap):
        totals = aggregate[rng.integers(0, n_groups, size=n_groups)].sum(axis=0)
        for j in range(len(arrays)):
            start = 1 + j * width
            samples[i, j] = (totals[start]/totals[0],
                             np.abs(totals[start+2:start+width]).sum()/totals[0],
                             totals[start+1]/totals[0])
    limits = np.quantile(samples, [.025, .975], axis=0)
    for j, model in enumerate(models.values()):
        for k, metric in enumerate(("accuracy", "ece", "brier")):
            model[metric + "_ci95"] = limits[:, j, k].tolist()
    result.update(bootstrap_seed=int(seed), doi_groups=n_groups,
                  bootstrap_method="shared DOI draws; record-weighted; percentile 95% intervals")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--probability-column", action="append", help="Explicit column; repeat for paired models.")
    parser.add_argument("--label-column", default="y", help="Use gold_label for existing holdout exports.")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--bootstrap", type=int, default=0, help="DOI replicates; 5000 reproduces the reported intervals.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table; no files are written.")
    args = parser.parse_args(argv)
    try:
        data = load_predictions(args.csv, probability_columns=args.probability_column, label_column=args.label_column)
        result = evaluate_predictions(data.labels, data.probabilities, bins=args.bins,
                                      dois=data.dois, bootstrap=args.bootstrap, seed=args.seed)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, indent=2, allow_nan=False))
        return result
    width = max(5, *(len(name) for name in result["models"]))
    print(f"{'Model':<{width}} {'n':>6} {'Accuracy':>10} {'ECE':>10} {'Brier':>10}")
    for name, model in result["models"].items():
        print(f"{name:<{width}} {model['n']:>6} {model['accuracy']:>10.4f} {model['ece']:>10.4f} {model['brier']:>10.4f}")
    if args.bootstrap:
        print(f"95% DOI bootstrap intervals ({args.bootstrap} shared replicates; seed {args.seed}):")
        for name, model in result["models"].items():
            e, b = model["ece_ci95"], model["brier_ci95"]
            print(f"{name:<{width}} ECE [{e[0]:.4f}, {e[1]:.4f}]  Brier [{b[0]:.4f}, {b[1]:.4f}]")
    return result


if __name__ == "__main__":
    main()
