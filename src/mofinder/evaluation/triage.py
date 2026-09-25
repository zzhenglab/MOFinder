"""Re-evaluate saved abstract-screening responses against the current reference.

Analysis reloads the editable human reference, retains unscored publications in
coverage denominators, and writes a separate analysis directory for each call.
The publication bootstrap and classification calculations follow the original
abstract-triage notebook.
"""

from collections import Counter
from datetime import datetime, timezone
from functools import partial
import hashlib
import itertools
import json
from pathlib import Path
from types import MappingProxyType
import uuid

import numpy as np
from scipy.stats import binomtest

from mofinder.display import display_path, display_paths
from mofinder.run_paths import create_run_directory
from mofinder.literature.triage import (
    GT_COLUMNS, read_table, doi_key, digest, save_csv, votes,
    divide, metric_values, confusion, interval, wilson, human_agreement,
)

def _load_saved_rows(folder):
    # The append-only journal is authoritative when both files exist.
    # It includes responses newer than the last predictions.csv checkpoint.
    journal = folder / "responses.jsonl"
    if journal.is_file() and journal.stat().st_size:
        rows = []
        with journal.open(encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Malformed saved response at {journal}, line {line_number}.") from error
                if not isinstance(row, dict):
                    raise ValueError(f"Response line {line_number} is not a record: {journal}")
                rows.append(row)
        return rows, journal
    csv_path = folder / "predictions.csv"
    if csv_path.is_file():
        return read_table(csv_path)[1], csv_path
    raise FileNotFoundError(f"No saved predictions found in {folder}")


def _read_manifest(folder):
    path = folder / "run_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing run_manifest.json in {folder}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid run manifest: {path}")
    return data


def _prediction_exists(folder):
    return any((folder / name).is_file() and (folder / name).stat().st_size
               for name in ["responses.jsonl", "predictions.csv"])


def select_saved_run(results_root):
    """Select the newest completed run with saved responses in results_root."""
    # Search only immediate run directories under results_root.
    results_root = Path(results_root).expanduser().resolve()
    if not results_root.is_dir():
        raise FileNotFoundError(
            f"No screening output directory found: {results_root}. "
            "Provide an existing completed screening run folder."
        )
    candidates, ignored = [], []
    for folder in sorted(results_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("analysis_") or not _prediction_exists(folder):
            continue
        try:
            manifest = _read_manifest(folder)
        except (ValueError, FileNotFoundError) as error:
            ignored.append(f"{folder.name}: {error}")
            continue
        if manifest.get("completed") is not True:
            ignored.append(f"{folder.name}: screening not marked completed")
            continue
        try:
            created = datetime.fromisoformat(str(manifest["created_utc"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            timestamp = created.timestamp()
        except (KeyError, ValueError):
            timestamp = max((folder / n).stat().st_mtime for n in
                            ["responses.jsonl", "predictions.csv"] if (folder / n).is_file())
        candidates.append((timestamp, folder.name, folder.resolve(), manifest))
    for warning in ignored:
        print("Not auto-selected:", display_paths(warning))
    if not candidates:
        raise FileNotFoundError("No completed screening run with saved results was found. No API calls were made.")
    candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    print(f"Found {len(candidates)} completed run(s). Selecting the newest screening run.")
    for _, _, folder, _ in candidates[:5]:
        print("  ", display_path(folder))
    return candidates[0][2]


def load_saved_run(run_dir, ground_truth_file, *, output_dir=None,
                   bootstraps=50_000, statistics_seed=42):
    """Validate saved responses and create a new analysis context.

    Parameters are explicit so analyses can be reproduced from scripts and
    notebooks. Pass the screening manifest's bootstrap count and statistics seed
    to reproduce its analysis settings. Original responses are never modified.
    """
    SCREENING_RUN_DIR = Path(run_dir).expanduser().resolve()
    _source_manifest = _read_manifest(SCREENING_RUN_DIR)
    if not isinstance(bootstraps, int) or isinstance(bootstraps, bool) or bootstraps < 1:
        raise ValueError("bootstraps must be a positive integer.")
    if not isinstance(statistics_seed, int) or isinstance(statistics_seed, bool) or statistics_seed < 0:
        raise ValueError("statistics_seed must be a non-negative integer.")
    BOOTSTRAPS = bootstraps
    STATISTICS_SEED = statistics_seed
    RUN_ID = str(_source_manifest.get("run_id", SCREENING_RUN_DIR.name))
    _saved_rows, PREDICTION_SOURCE = _load_saved_rows(SCREENING_RUN_DIR)
    if not _saved_rows:
        raise ValueError("The selected run contains no prediction rows.")
    if ("recorded_requests" in _source_manifest and
            len(_saved_rows) != int(_source_manifest["recorded_requests"])):
        raise ValueError("The saved response count differs from the completed-run manifest. "
                         "Restore the complete predictions before reanalysis.")
    if _source_manifest.get("completed") is not True:
        raise ValueError("The selected screening run is incomplete. Finish screening before reanalysis.")

    _seen = set()
    for row in _saved_rows:
        required = {"Run ID", "DOI", "Configuration", "Round", "Agent_YN", "Status"}
        if not required.issubset(row):
            raise ValueError(f"Missing saved-prediction fields: {sorted(required - row.keys())}")
        if str(row["Run ID"]) != RUN_ID:
            raise ValueError("Saved predictions contain a different Run ID. No files were changed.")
        row["DOI"] = doi_key(row["DOI"])
        numeric_round = float(row["Round"])
        if not numeric_round.is_integer() or numeric_round < 1:
            raise ValueError(f"Invalid saved round: {row['Round']}")
        row["Round"] = int(numeric_round)
        if row["Status"] == "ok" and row["Agent_YN"] not in {"Y", "N"}:
            raise ValueError("A saved answer marked ok is not a valid Y/N label.")
        key = (row["Configuration"], row["Round"], row["DOI"])
        if key in _seen:
            raise ValueError(f"Duplicate saved prediction: {key}")
        _seen.add(key)

    # Use the configurations and number of rounds that actually generated this run.
    MODELS = _source_manifest.get("models", [])
    N_ROUNDS = int(_source_manifest.get("rounds", 0))
    if (not MODELS or N_ROUNDS < 1 or
            any(not isinstance(m, dict) or not m.get("name") for m in MODELS)):
        raise ValueError("The saved manifest lacks valid model configurations or round count.")
    _names = [m["name"] for m in MODELS]
    if len(_names) != len(set(_names)):
        raise ValueError("Duplicate configuration names in the saved manifest.")
    if any(r["Configuration"] not in _names or r["Round"] > N_ROUNDS for r in _saved_rows):
        raise ValueError("Saved predictions and the saved model/round configuration disagree.")

    GT_FILE = Path(ground_truth_file).expanduser().resolve()
    if SCREENING_RUN_DIR.parent in GT_FILE.parents:
        raise ValueError("Select the editable ground-truth workbook outside the screening output directory, not a saved snapshot.")
    headers, ground_truth, sheet_names = read_table(GT_FILE)
    if len(sheet_names) != 1 or len(headers) != len(GT_COLUMNS) or set(headers) != set(GT_COLUMNS):
        raise ValueError("Use the one-sheet, 13-column ground-truth workbook supplied with the abstract-triage workflow.")
    GT_BY_DOI = {}
    for row in ground_truth:
        key = doi_key(row["DOI"])
        if key in GT_BY_DOI:
            raise ValueError(f"Duplicate reference DOI: {key}")
        if row["Consensus GT"].strip().upper() not in {"Y", "N"}:
            raise ValueError(f"Non-binary consensus for {key}; resolve it explicitly before evaluation.")
        GT_BY_DOI[key] = row
    if not GT_BY_DOI:
        raise ValueError("The current ground-truth file is empty.")

    # Recover the original scheduled DOI set where possible, without loading abstracts.
    PAPER_IDS = {r["DOI"] for r in _saved_rows}
    _scheduled_source = "DOIs present in the saved response records"
    _old_reference = SCREENING_RUN_DIR / "reference_used.csv"
    _not_screened = SCREENING_RUN_DIR / "reference_not_screened.csv"
    if _source_manifest.get("benchmark_only") and _old_reference.is_file() and _not_screened.is_file():
        old_rows = read_table(_old_reference)[1]
        skipped = {doi_key(r["DOI"]) for r in read_table(_not_screened)[1]}
        scheduled = {doi_key(r["DOI"]) for r in old_rows} - skipped
        if len(scheduled) == int(_source_manifest.get("scheduled_publications", -1)) and PAPER_IDS <= scheduled:
            PAPER_IDS = scheduled
            _scheduled_source = "original reference DOI list minus original reference_not_screened.csv"
    if len(PAPER_IDS) != int(_source_manifest.get("scheduled_publications", len(PAPER_IDS))):
        raise ValueError("Cannot recover the original scheduled DOI set exactly from the saved files. "
                         "No analysis was written; restore reference_used.csv and reference_not_screened.csv from that run.")


    ANALYSIS_ID = uuid.uuid4().hex
    if output_dir is None:
        ANALYSIS_DIR = create_run_directory(SCREENING_RUN_DIR, prefix="analysis")
    else:
        ANALYSIS_DIR = Path(output_dir).expanduser().resolve()
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=False)
    MANIFEST = dict(_source_manifest)
    MANIFEST.update({
        "analysis_id": ANALYSIS_ID,
        "analysis_created_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_only": True,
        "bootstrap_replicates": BOOTSTRAPS,
        "statistics_seed": STATISTICS_SEED,
        "source_run_directory": str(SCREENING_RUN_DIR),
        "prediction_source_file": str(PREDICTION_SOURCE),
        "prediction_file_sha256": hashlib.sha256(PREDICTION_SOURCE.read_bytes()).hexdigest(),
        "reference_file": str(GT_FILE),
        "screening_reference_publications": _source_manifest.get("reference_publications"),
        "reference_publications": len(GT_BY_DOI),
        "screening_reference_labels_sha256": _source_manifest.get("reference_labels_sha256"),
        "reference_file_sha256": hashlib.sha256(GT_FILE.read_bytes()).hexdigest(),
        "reference_labels_sha256": digest(sorted((k, r["Consensus GT"].strip().upper()) for k, r in GT_BY_DOI.items())),
        "scheduled_doi_source": _scheduled_source,
    })
    (ANALYSIS_DIR / "analysis_manifest.json").write_text(json.dumps(MANIFEST, indent=2, ensure_ascii=False), encoding="utf-8")
    save_csv(ground_truth, ANALYSIS_DIR / "reference_used.csv", GT_COLUMNS)
    _changes = []
    if _old_reference.is_file():
        _old = {doi_key(r["DOI"]): r["Consensus GT"].strip().upper() for r in read_table(_old_reference)[1]}
        _new = {key: row["Consensus GT"].strip().upper() for key, row in GT_BY_DOI.items()}
        for key in sorted(set(_old) | set(_new)):
            if _old.get(key) != _new.get(key):
                _changes.append({"DOI": key, "Screening-time GT": _old.get(key, ""), "Current GT": _new.get(key, ""),
                                 "Change": "Added DOI" if key not in _old else "Removed DOI" if key not in _new else "Label changed"})
    save_csv(_changes, ANALYSIS_DIR / "GT_changes_since_screening.csv",
             ["DOI", "Screening-time GT", "Current GT", "Change"])
    return {
        "run_id": RUN_ID,
        "run_dir": SCREENING_RUN_DIR,
        "output_dir": ANALYSIS_DIR,
        "prediction_source": PREDICTION_SOURCE,
        "ground_truth_file": GT_FILE,
        "ground_truth": ground_truth,
        "ground_truth_by_doi": GT_BY_DOI,
        "paper_ids": PAPER_IDS,
        "rows": _saved_rows,
        "models": MODELS,
        "rounds": N_ROUNDS,
        "bootstraps": BOOTSTRAPS,
        "statistics_seed": STATISTICS_SEED,
        "manifest": MANIFEST,
        "ground_truth_changes": _changes,
    }


METRICS = ("Accuracy", "Precision", "Recall", "Specificity", "F1", "Balanced accuracy", "NPV", "MCC")
FORMULAS = MappingProxyType({
    "Accuracy": "(TP+TN)/(TP+FP+TN+FN)", "Precision": "TP/(TP+FP)",
    "Recall": "TP/(TP+FN)", "Specificity": "TN/(TN+FP)",
    "F1": "2*TP/(2*TP+FP+FN)", "Balanced accuracy": "(Recall+Specificity)/2",
    "NPV": "TN/(TN+FN)", "MCC": "(TP*TN-FP*FN)/sqrt((TP+FP)*(TP+FN)*(TN+FP)*(TN+FN))",
})


def evaluate_counts(y, p, configuration, round_number, reference_n, scheduled_n, scope,
                    *, bootstraps=50_000, statistics_seed=42):
    """Calculate classification estimates and publication-level intervals."""
    c = confusion(y, p)
    tp, fp, tn, fn = (int(v) for v in c)
    n = int(c.sum())
    values = metric_values(c)
    base = {"Configuration": configuration, "Round": round_number, "Scope": scope,
            "Reference N": reference_n, "Scheduled reference N": scheduled_n, "Scored N": n,
            "Unscored reference N": reference_n - n,
            "Coverage of reference": float(divide(n, reference_n)),
            "TP": tp, "FP": fp, "TN": tn, "FN": fn}
    summary = {**base, **{k: float(v) for k, v in values.items()}}
    rng = np.random.default_rng(statistics_seed)
    resampled = metric_values(rng.multinomial(n, c / n, size=bootstraps)) if n else {}
    ratios = {"Accuracy": (tp + tn, n), "Precision": (tp, tp + fp),
              "Recall": (tp, tp + fn), "Specificity": (tn, tn + fp), "NPV": (tn, tn + fn)}
    details = []
    for name in METRICS:
        if name in ratios:
            numerator, denominator = ratios[name]
            low, high = wilson(numerator, denominator)
            method, valid_bootstraps = "Wilson", ""
        else:
            numerator, denominator = "", ""
            low, high, valid_bootstraps = interval(resampled.get(name, []))
            method = "Publication percentile bootstrap"
        details.append({**base, "Metric": name, "Estimate": float(values[name]),
                        "CI lower": float(low), "CI upper": float(high), "CI method": method,
                        "Numerator": numerator, "Denominator": denominator,
                        "Valid bootstrap draws": valid_bootstraps, "Formula": FORMULAS[name]})
    return summary, details

def evaluate_run(context):
    """Write classification, paired-comparison, and human-agreement tables.

    Failed or missing responses remain unscored. Each configuration's coverage
    is reported against the complete current reference, and paired model
    comparisons use only publications scored by both models.
    """
    RUN_ID = context["run_id"]
    GT_BY_DOI = context["ground_truth_by_doi"]
    PAPER_IDS = context["paper_ids"]
    MODELS = context["models"]
    N_ROUNDS = context["rounds"]
    BOOTSTRAPS = context["bootstraps"]
    STATISTICS_SEED = context["statistics_seed"]
    OUTPUT_DIR = context["output_dir"]
    ground_truth = context["ground_truth"]
    LIVE_RESULTS = {"rows": context["rows"]}
    _counts = partial(evaluate_counts, bootstraps=BOOTSTRAPS, statistics_seed=STATISTICS_SEED)

    prediction_index = {}
    for r in LIVE_RESULTS["rows"]:
        if r["Run ID"] != RUN_ID:
            raise ValueError("A response belongs to a different run.")
        key = (r["Configuration"], int(r["Round"]), r["DOI"])
        if key in prediction_index:
            raise ValueError(f"Duplicate saved prediction: {key}")
        prediction_index[key] = r

    def pairs_for(name, round_number, ids):
        data = []
        for key in ids:
            pred = prediction_index.get((name, round_number, key), {})
            if pred.get("Status") == "ok" and pred.get("Agent_YN") in {"Y", "N"}:
                data.append((key, int(GT_BY_DOI[key]["Consensus GT"].strip().upper() == "Y"), int(pred["Agent_YN"] == "Y")))
        return data

    metrics, metric_details, paper_results, sensitivity, shared_metrics, shared_details = [], [], [], [], [], []
    unanimous_ids = [k for k, r in GT_BY_DOI.items() if votes(r) in {(4, 0), (0, 4)}]
    nonunanimous_ids = [k for k in GT_BY_DOI if k not in set(unanimous_ids)]
    reference_ids = list(GT_BY_DOI)
    for round_number in range(1, N_ROUNDS + 1):
        all_valid = []
        for cfg in MODELS:
            name = cfg["name"]
            pairs = pairs_for(name, round_number, reference_ids)
            ids = {x[0] for x in pairs}
            all_valid.append(ids)
            result, details = _counts([x[1] for x in pairs], [x[2] for x in pairs], name, round_number,
                                             len(reference_ids), len(PAPER_IDS & set(reference_ids)), "Full reference")
            metrics.append(result)
            metric_details.extend(details)
            for key, gt in GT_BY_DOI.items():
                pred = prediction_index.get((name, round_number, key), {})
                label = pred.get("Agent_YN", "") if pred.get("Status") == "ok" else ""
                truth = gt["Consensus GT"].strip().upper()
                outcome = {( "Y", "Y"): "TP", ("N", "Y"): "FP", ("N", "N"): "TN", ("Y", "N"): "FN"}.get((truth, label), "Unscored")
                paper_results.append({**gt, "Normalized DOI": key, "Configuration": name, "Round": round_number,
                                      "Agent_YN": label, "Outcome": outcome,
                                      "Status": pred.get("Status", "not_screened" if key not in PAPER_IDS else "not_returned"),
                                      "Error": pred.get("Error", "")})
            for scope, subset in [("Unanimous four-rater subset", unanimous_ids),
                                  ("Non-unanimous or ambiguous subset", nonunanimous_ids)]:
                sub = pairs_for(name, round_number, subset)
                result, _ = _counts([x[1] for x in sub], [x[2] for x in sub], name, round_number,
                                           len(subset), len(PAPER_IDS & set(subset)), scope)
                sensitivity.append(result)
        common_ids = [k for k in reference_ids if all(k in ids for ids in all_valid)]
        for cfg in MODELS:
            pairs = pairs_for(cfg["name"], round_number, common_ids)
            result, details = _counts([x[1] for x in pairs], [x[2] for x in pairs], cfg["name"], round_number,
                                             len(reference_ids), len(PAPER_IDS & set(reference_ids)), "Shared complete-case")
            shared_metrics.append(result)
            shared_details.extend(details)

    paired_comparisons = []
    for round_number in range(1, N_ROUNDS + 1):
        for cfg_a, cfg_b in itertools.combinations(MODELS, 2):
            a = {k: (y, p) for k, y, p in pairs_for(cfg_a["name"], round_number, reference_ids)}
            b = {k: (y, p) for k, y, p in pairs_for(cfg_b["name"], round_number, reference_ids)}
            common = [k for k in reference_ids if k in a and k in b]
            n = len(common)
            base = {"Model A": cfg_a["name"], "Model B": cfg_b["name"], "Round": round_number, "Common scored N": n}
            if not n:
                paired_comparisons.append({**base, "Note": "No common valid predictions"})
                continue
            y = np.array([a[k][0] for k in common]); pa = np.array([a[k][1] for k in common]); pb = np.array([b[k][1] for k in common])
            a_only = int(np.sum((pa == y) & (pb != y))); b_only = int(np.sum((pb == y) & (pa != y)))
            pvalue = binomtest(a_only, a_only + b_only, p=0.5).pvalue if a_only + b_only else 1.0
            # Resample the eight joint (truth, A prediction, B prediction) categories.
            frequencies = np.bincount(y * 4 + pa * 2 + pb, minlength=8)
            draws = np.random.default_rng(STATISTICS_SEED).multinomial(n, frequencies / n, size=BOOTSTRAPS)
            bits = np.arange(8); yy = bits // 4; aa = (bits // 2) % 2; bb = bits % 2
            def counts_for(pred_bits):
                masks = [(yy == 1) & (pred_bits == 1), (yy == 0) & (pred_bits == 1),
                         (yy == 0) & (pred_bits == 0), (yy == 1) & (pred_bits == 0)]
                return np.column_stack([draws[:, mask].sum(axis=1) for mask in masks])
            va, vb = metric_values(confusion(y, pa)), metric_values(confusion(y, pb))
            ba, bboot = metric_values(counts_for(aa)), metric_values(counts_for(bb))
            for metric in ["Accuracy", "Precision", "Recall", "F1", "Balanced accuracy"]:
                low, high, valid = interval(ba[metric] - bboot[metric])
                paired_comparisons.append({**base, "Metric": metric,
                    "A minus B": float(va[metric] - vb[metric]), "CI lower": float(low), "CI upper": float(high),
                    "A correct only": a_only, "B correct only": b_only,
                    "McNemar exact p (accuracy; unadjusted)": pvalue,
                    "Valid paired bootstrap draws": valid, "Note": "Differences use fractions; multiply by 100 for percentage points."})

    run_summary = []
    for cfg in MODELS:
        rows = [r for r in metrics if r["Configuration"] == cfg["name"]]
        for metric in METRICS:
            values = np.array([r[metric] for r in rows]); values = values[np.isfinite(values)]
            run_summary.append({"Configuration": cfg["name"], "Metric": metric,
                                "Requested rounds": N_ROUNDS, "Defined rounds": len(values),
                                "Mean": float(values.mean()) if len(values) else np.nan,
                                "SD across rounds": float(values.std(ddof=1)) if len(values) > 1 else np.nan})

    for name, rows in [("metrics.csv", metrics), ("metrics_with_CI_and_calculations.csv", metric_details),
                       ("per_paper_results.csv", paper_results),
                       ("error_cases.csv", [r for r in paper_results if r["Outcome"] in {"FP", "FN"}]),
                       ("unscored_cases.csv", [r for r in paper_results if r["Outcome"] == "Unscored"]),
                       ("sensitivity_analysis.csv", sensitivity),
                       ("shared_complete_case_metrics.csv", shared_metrics),
                       ("shared_complete_case_intervals.csv", shared_details),
                       ("paired_model_comparisons.csv", paired_comparisons), ("round_summary.csv", run_summary)]:
        save_csv(rows, OUTPUT_DIR / name)

    pattern_counts = Counter(votes(r) for r in ground_truth)
    agreement = human_agreement(ground_truth, bootstraps=BOOTSTRAPS, seed=STATISTICS_SEED)
    cohen = []
    for i, j in itertools.combinations(range(1, 5), 2):
        labels = [(r[f"Annotator {i}"].strip().upper(), r[f"Annotator {j}"].strip().upper()) for r in ground_truth]
        labels = [(a, b) for a, b in labels if a in {"Y", "N"} and b in {"Y", "N"}]
        n = len(labels)
        if n:
            po = sum(a == b for a, b in labels) / n
            pa = sum(a == "Y" for a, b in labels) / n; pb = sum(b == "Y" for a, b in labels) / n
            pe = pa * pb + (1 - pa) * (1 - pb)
            kappa = float(divide(po - pe, 1 - pe))
        else:
            po, kappa = np.nan, np.nan
        cohen.append({"Annotator A": i, "Annotator B": j, "Paired papers": n, "Raw agreement": po, "Cohen kappa": kappa})
    vote_summary = [{"Y votes": y, "N votes": n, "Ambiguous or missing": 4 - y - n,
                     "Vote pattern": f"{y}Y / {n}N" + (f" / {4-y-n} ambiguous" if y + n < 4 else ""),
                     "Publications": count} for (y, n), count in sorted(pattern_counts.items(), reverse=True)]
    resolution_summary = [{"Resolution method": name, "Publications": count}
                          for name, count in Counter(r["Resolution method"] for r in ground_truth).items()]
    reference_summary = [{"Consensus GT": label, "Publications": sum(r["Consensus GT"].strip().upper() == label for r in ground_truth)}
                         for label in ["Y", "N"]]
    for name, rows in [("human_agreement.csv", agreement), ("annotator_pairwise_agreement.csv", cohen),
                       ("vote_patterns.csv", vote_summary), ("resolution_methods.csv", resolution_summary),
                       ("reference_distribution.csv", reference_summary)]:
        save_csv(rows, OUTPUT_DIR / name)
    context.update({
        "metrics": metrics,
        "metric_details": metric_details,
        "paper_results": paper_results,
        "sensitivity": sensitivity,
        "shared_metrics": shared_metrics,
        "shared_details": shared_details,
        "paired_comparisons": paired_comparisons,
        "run_summary": run_summary,
        "agreement": agreement,
        "cohen": cohen,
        "vote_summary": vote_summary,
        "resolution_summary": resolution_summary,
        "reference_summary": reference_summary,
    })
    return context
