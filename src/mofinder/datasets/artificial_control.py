"""Training-only artificial negatives; their N labels are experimental controls."""
from collections import Counter
from copy import deepcopy
import json
import math
import random

import numpy as np

from mofinder.training.records import INPUT_FIELDS as FIELDS
NUMERIC = FIELDS[4:]


def inputs(record):
    return json.loads(record["messages"][1]["content"])


def condition_key(values):
    # The original baseline uses case/whitespace normalization and eight-decimal
    # numerical keys. Reuse it for collision protection, not neighbor matching.
    from mofinder.datasets.prepare import forced_question_condition_key
    return forced_question_condition_key(values)


def _distance(value, parent, scale):
    if value is None or parent is None:
        return None
    return abs(value - parent) / scale


def generate(train, holdout, neighbors, train_sources, holdout_sources, seed):
    """Keep P slots; replace every N using a training-P anchor and exact mask.

    Donor values come only from training P. Training N determines change masks,
    target numeric distances and marginal sampling weights; source evidence is
    never used to assert that a generated condition failed. Holdout inputs are
    used only as label-blind exact-condition and chemical-cluster blacklists.
    """
    rng = random.Random(seed)
    conditions = [inputs(record) for record in train]
    positive_rows = [i for i, r in enumerate(train) if r["messages"][2]["content"] == "P"]
    negative_rows = [i for i, r in enumerate(train) if r["messages"][2]["content"] == "N"]
    positives = [conditions[i] for i in positive_rows]
    real_negatives = [conditions[i] for i in negative_rows]
    by_row = {item["baseline_row_1based"]: item for item in neighbors}
    pools, weights, scales = {}, {}, {}
    for field in FIELDS:
        counts = Counter(p[field] for p in positives)
        pools[field] = sorted(counts, key=lambda x: (x is not None, str(x)))
        targets = Counter(conditions[i][field] for i in negative_rows
                          if field in by_row[i + 1]["changed_fields"])
        # Add-one smoothing allows values absent from reconstructed negatives.
        weights[field] = {value: targets[value] + 1 for value in pools[field]}
        if field in NUMERIC:
            values = [p[field] for p in positives if p[field] is not None]
            q25, q75 = np.percentile(values, [25, 75])
            scales[field] = float(q75 - q25) or float(np.std(values)) or 1.0

    original_train_keys = {condition_key(c) for c in conditions}
    holdout_keys = {condition_key(inputs(r)) for r in holdout}
    holdout_clusters = {row["cluster_key"] for row in holdout_sources.values()}
    component_maps = {field: {} for field in (FIELDS[0], FIELDS[1], FIELDS[3])}
    # Source cluster components preserve multi-linker/solvent set normalization.
    for row_number in positive_rows:
        row = train_sources[row_number + 1]
        metal, rest = row["cluster_key"].split("|linker=", 1)
        linker, solvent = rest.split("|solvent=", 1)
        for field, component in zip(component_maps, (metal[6:], linker, solvent)):
            value = conditions[row_number][field]
            old = component_maps[field].setdefault(value, component)
            if old != component:
                raise ValueError(f"Ambiguous chemical component for {field}: {value!r}")

    def cluster_key(candidate):
        return ("metal=" + component_maps[FIELDS[0]][candidate[FIELDS[0]]]
                + "|linker=" + component_maps[FIELDS[1]][candidate[FIELDS[1]]]
                + "|solvent=" + component_maps[FIELDS[3]][candidate[FIELDS[3]]])

    used = set()
    output = list(train)
    provenance = []
    rejected = Counter()
    fallback_counts = Counter()
    for slot in negative_rows:
        details = by_row[slot + 1]
        anchor_row = details["nearest_positive_row_1based"]
        parent = conditions[anchor_row - 1]
        original = conditions[slot]
        changed = [field for field in FIELDS if original[field] != parent[field]]
        if changed != details["changed_fields"] or not changed:
            raise ValueError(f"Reference mask mismatch at training row {slot + 1}")
        options, wide_options = {}, {}
        for field in changed:
            alternatives = [v for v in pools[field] if v != parent[field]]
            if not alternatives:
                raise ValueError(f"No training-P donor for {field}, training row {slot + 1}")
            wide_options[field] = alternatives
            if field in NUMERIC and parent[field] is not None and original[field] is not None:
                target = abs(original[field] - parent[field])
                finite = [v for v in alternatives if v is not None]
                options[field] = sorted(finite, key=lambda v: (abs(abs(v - parent[field]) - target), v))[:32]
            else:
                options[field] = alternatives
            if not options[field]:
                options[field] = alternatives

        def score(candidate):
            penalty = 0.0
            for field in changed:
                penalty += 2.0 * ((candidate[field] is None) != (original[field] is None))
                if field in NUMERIC:
                    d0 = _distance(original[field], parent[field], scales[field])
                    d1 = _distance(candidate[field], parent[field], scales[field])
                    if d0 is not None and d1 is not None:
                        penalty += abs(math.log1p(d0) - math.log1p(d1))
            return penalty

        best = None
        best_score = float("inf")
        attempts = 0
        used_wide_pool = False
        # A broad-pool fallback relaxes distance matching, never the mask/reference.
        for broad, limit in ((False, 96), (True, 1024)):
            candidates = wide_options if broad else options
            drawn = {field: rng.choices(values, weights=[weights[field][v] for v in values], k=limit)
                     for field, values in candidates.items()}
            for trial in range(limit):
                attempts += 1
                candidate = parent.copy()
                for field in changed:
                    candidate[field] = drawn[field][trial]
                key = condition_key(candidate)
                if key in original_train_keys:
                    rejected["original_training_condition"] += 1
                    continue
                if key in holdout_keys:
                    rejected["holdout_condition"] += 1
                    continue
                if key in used:
                    rejected["duplicate_synthetic_condition"] += 1
                    continue
                if cluster_key(candidate) in holdout_clusters:
                    rejected["holdout_chemical_cluster"] += 1
                    continue
                loss = score(candidate)
                if loss < best_score:
                    best, best_score = candidate, loss
                    used_wide_pool = broad
            if best is not None:
                break
        if best is None:
            # Never silently reuse a real negative or duplicate to fill a slot.
            raise ValueError(f"No novel synthetic condition for row {slot + 1}, anchor {anchor_row}, "
                             f"mask {changed}; exact reference/mask constraints cannot be relaxed silently.")
        if [f for f in FIELDS if best[f] != parent[f]] != changed:
            raise AssertionError("Generated mask differs from prescribed mask")
        key = condition_key(best)
        used.add(key)
        record = deepcopy(train[slot])
        record["messages"][1]["content"] = json.dumps(best, ensure_ascii=False, allow_nan=False)
        output[slot] = record
        missingness_relaxed = [f for f in changed if (best[f] is None) != (original[f] is None)]
        fallback_counts["broad_donor_pool_rows"] += used_wide_pool
        fallback_counts["missingness_transition_relaxed_rows"] += bool(missingness_relaxed)
        provenance.append({
            "baseline_row_1based": slot + 1, "reference_positive_row_1based": anchor_row,
            "reference_doi": train_sources[anchor_row]["doi_norm"],
            "original_negative_doi": train_sources[slot + 1]["doi_norm"],
            "changed_fields": changed, "n_changed_fields": len(changed),
            "missingness_relaxed_fields": missingness_relaxed,
            "broad_pool_fallback": used_wide_pool, "candidate_attempts": attempts,
            "numeric_missingness_matching_loss": best_score,
            "original_negative_values": {f: original[f] for f in changed},
            "reference_positive_values": {f: parent[f] for f in changed},
            "synthetic_values": {f: best[f] for f in changed},
            "label_status": "Artificial N; experimental failure not established",
        })

    synthetic = [inputs(output[i]) for i in negative_rows]
    diagnostics = {
        "seed": seed, "positive_rows_unchanged": len(positive_rows),
        "negative_rows_replaced": len(negative_rows), "positive_rows_dropped": 0,
        "negative_slots_dropped": 0, "original_negative_rows_replaced": len(negative_rows),
        "reference_identity_and_usage_exact": True, "change_masks_exact": True,
        "training_P_only_donor_values": True,
        "rejected_candidates": dict(rejected), "relaxations": dict(fallback_counts),
        "numeric_scales_training_positive_IQR": scales,
        "known_training_condition_collisions": len(used & original_train_keys),
        "holdout_condition_collisions": len(used & holdout_keys),
        "holdout_cluster_collisions": sum(cluster_key(c) in holdout_clusters for c in synthetic),
        "unique_synthetic_negatives": len(used), "field_diagnostics": {},
    }
    for field in FIELDS:
        real_counts = Counter(v[field] for v in real_negatives)
        syn_counts = Counter(v[field] for v in synthetic)
        all_values = set(real_counts) | set(syn_counts)
        diagnostic = {
            "real_missing": real_counts[None], "synthetic_missing": syn_counts[None],
            "marginal_total_variation": sum(abs(real_counts[v] - syn_counts[v]) for v in all_values) / (2 * len(synthetic)),
            "real_changed_rows": sum(field in row["changed_fields"] for row in provenance),
            "synthetic_changed_rows": sum(field in row["changed_fields"] for row in provenance),
            "changed_target_outside_positive_support_rows": sum(
                field in row["changed_fields"] and real[field] not in weights[field]
                for row, real in zip(provenance, real_negatives)),
            "missingness_transition_relaxed_rows": sum(field in row["missingness_relaxed_fields"] for row in provenance),
        }
        if field in NUMERIC:
            real_distances, syn_distances = [], []
            for p, real, syn in zip(provenance, real_negatives, synthetic):
                if field not in p["changed_fields"]:
                    continue
                parent = conditions[p["reference_positive_row_1based"] - 1]
                a = _distance(real[field], parent[field], scales[field])
                b = _distance(syn[field], parent[field], scales[field])
                if a is not None and b is not None:
                    real_distances.append(a)
                    syn_distances.append(b)
            diagnostic["paired_numeric_distance_count"] = len(real_distances)
            diagnostic["normalized_distance_mean_absolute_error"] = (
                float(np.mean(np.abs(np.array(real_distances) - np.array(syn_distances)))) if real_distances else None)
            diagnostic["real_median_normalized_distance"] = float(np.median(real_distances)) if real_distances else None
            diagnostic["synthetic_median_normalized_distance"] = float(np.median(syn_distances)) if syn_distances else None
            diagnostic["numeric_direction_reversed_rows"] = sum(
                field in row["changed_fields"]
                and row["reference_positive_values"][field] is not None
                and real[field] is not None and syn[field] is not None
                and (real[field] - row["reference_positive_values"][field])
                    * (syn[field] - row["reference_positive_values"][field]) < 0
                for row, real, syn in zip(provenance, real_negatives, synthetic))
        diagnostics["field_diagnostics"][field] = diagnostic
    return output, provenance, diagnostics


def processed_condition_keys(positive_csv, negative_csv):
    """Canonical conditions from both processed CSVs, including filtered rows."""
    import pandas as pd
    from mofinder.datasets.prepare import row_to_conditions

    keys = set()
    for path in (positive_csv, negative_csv):
        for _, row in pd.read_csv(path, low_memory=False).iterrows():
            keys.add(condition_key(row_to_conditions(row)))
    return keys


def generate_count_matched(train, holdout, neighbors, train_sources,
                           holdout_sources, seed, *, excluded_condition_keys=()):
    """Replace training N while matching only the number of changed fields.

    Each N retains its nearest training-P anchor and its original distance k
    from that anchor. Choose k distinct mutable fields uniformly, without using
    the identities of the original changed fields. A selected subset stays
    fixed throughout rejection sampling. Replacement values are independent
    empirical training-P draws, conditional on differing from the anchor;
    null is a donor value when present in training P. Neither the reconstructed
    negative values nor their numerical distances affect donor probabilities.

    Reject known conditions, holdout chemical clusters, and synthetic duplicates.
    Rejection conditions the accepted distribution on these exclusions. An
    exhausted or unsuccessful subset raises an error rather than changing k,
    choosing a new subset, or quietly relaxing an exclusion. The retained k is
    measured against the selected anchor, not against every training positive.
    """
    from itertools import accumulate

    rng = random.Random(seed)
    conditions = [inputs(record) for record in train]
    positive_rows = [i for i, row in enumerate(train)
                     if row["messages"][2]["content"] == "P"]
    negative_rows = [i for i, row in enumerate(train)
                     if row["messages"][2]["content"] == "N"]
    if not positive_rows or not negative_rows:
        raise ValueError("Count-matched generation requires training P and N")
    if len(positive_rows) + len(negative_rows) != len(train):
        raise ValueError("Training records must have P or N labels")
    if any(set(values) != set(FIELDS) for values in conditions):
        raise ValueError("Count-matched generation requires exactly eight input fields")
    positive_row_numbers = {i + 1 for i in positive_rows}
    by_row = {row["baseline_row_1based"]: row for row in neighbors}
    counts = {field: Counter(conditions[i][field] for i in positive_rows)
              for field in FIELDS}
    pools = {field: sorted(counts[field], key=lambda value: (value is not None, str(value)))
             for field in FIELDS}
    donor_options = {}

    def options(field, parent_value):
        key = (field, parent_value)
        if key not in donor_options:
            values = [value for value in pools[field] if value != parent_value]
            cumulative = list(accumulate(counts[field][value] for value in values))
            donor_options[key] = values, cumulative
        return donor_options[key]

    original_keys = {condition_key(values) for values in conditions}
    holdout_keys = {condition_key(inputs(row)) for row in holdout}
    extra_keys = set(excluded_condition_keys)
    holdout_clusters = {row["cluster_key"] for row in holdout_sources.values()}
    component_maps = {field: {} for field in (FIELDS[0], FIELDS[1], FIELDS[3])}
    for slot in positive_rows:
        metal, rest = train_sources[slot + 1]["cluster_key"].split("|linker=", 1)
        linker, solvent = rest.split("|solvent=", 1)
        for field, component in zip(component_maps, (metal[6:], linker, solvent)):
            value = conditions[slot][field]
            old = component_maps[field].setdefault(value, component)
            if old != component:
                raise ValueError(f"Ambiguous chemical component for {field}: {value!r}")

    def cluster_key(candidate):
        return ("metal=" + component_maps[FIELDS[0]][candidate[FIELDS[0]]]
                + "|linker=" + component_maps[FIELDS[1]][candidate[FIELDS[1]]]
                + "|solvent=" + component_maps[FIELDS[3]][candidate[FIELDS[3]]])

    output = list(train)
    provenance, used = [], set()
    rejected = Counter()
    original_histogram, synthetic_histogram = Counter(), Counter()
    original_field_counts, synthetic_field_counts = Counter(), Counter()
    max_attempts = 100_000
    for slot in negative_rows:
        details = by_row[slot + 1]
        anchor_row = details["nearest_positive_row_1based"]
        if anchor_row not in positive_row_numbers:
            raise ValueError(f"Anchor {anchor_row} is not a training positive")
        parent = conditions[anchor_row - 1]
        original = conditions[slot]
        original_changed = [field for field in FIELDS if parent[field] != original[field]]
        if not original_changed or original_changed != details["changed_fields"]:
            raise ValueError(f"Reference mask mismatch at training row {slot + 1}")
        k = len(original_changed)
        mutable = [field for field in FIELDS if options(field, parent[field])[0]]
        if len(mutable) < k:
            raise ValueError(f"Only {len(mutable)} mutable fields for k={k} at row {slot + 1}")
        selected = set(rng.sample(mutable, k))
        changed = [field for field in FIELDS if field in selected]
        distributions = {field: options(field, parent[field]) for field in changed}
        support_size = math.prod(len(values) for values, _ in distributions.values())
        # Track small supports to report exhaustion without wasting the full bound.
        seen_combinations = set() if support_size <= max_attempts else None
        row_rejected = Counter()
        candidate = None
        for attempt in range(1, max_attempts + 1):
            drawn = parent.copy()
            for field, (values, cumulative) in distributions.items():
                drawn[field] = rng.choices(values, cum_weights=cumulative, k=1)[0]
            key = condition_key(drawn)
            reason = None
            if key in original_keys:
                reason = "original_training_condition"
            elif key in holdout_keys:
                reason = "holdout_condition"
            elif key in extra_keys:
                reason = "excluded_processed_condition"
            elif key in used:
                reason = "duplicate_synthetic_condition"
            elif cluster_key(drawn) in holdout_clusters:
                reason = "holdout_chemical_cluster"
            if reason is None:
                candidate = drawn
                break
            row_rejected[reason] += 1
            if seen_combinations is not None:
                seen_combinations.add(tuple(drawn[field] for field in changed))
                if len(seen_combinations) == support_size:
                    break
        if candidate is None:
            exhausted = seen_combinations is not None and len(seen_combinations) == support_size
            raise ValueError(
                f"No count-matched synthetic condition for row {slot + 1}, anchor {anchor_row}, "
                f"fixed mask {changed}, k={k}; "
                f"{'donor support exhausted' if exhausted else 'rejection limit reached'} "
                f"after {attempt} attempts. No mask or exclusion was relaxed.")
        if [field for field in FIELDS if candidate[field] != parent[field]] != changed:
            raise AssertionError("Generated mask differs from selected count-matched mask")
        used.add(condition_key(candidate))
        record = deepcopy(train[slot])
        record["messages"][1]["content"] = json.dumps(candidate, ensure_ascii=False, allow_nan=False)
        output[slot] = record
        rejected.update(row_rejected)
        original_histogram[k] += 1
        synthetic_histogram[len(changed)] += 1
        original_field_counts.update(original_changed)
        synthetic_field_counts.update(changed)
        provenance.append({
            "baseline_row_1based": slot + 1,
            "reference_positive_row_1based": anchor_row,
            "reference_doi": train_sources[anchor_row]["doi_norm"],
            "original_negative_doi": train_sources[slot + 1]["doi_norm"],
            "original_changed_fields": original_changed,
            "changed_fields": changed, "n_changed_fields": k,
            "n_mutable_fields": len(mutable),
            "same_change_mask_as_original": changed == original_changed,
            "candidate_attempts": attempt, "rejected_candidates": dict(row_rejected),
            "original_negative_values": {field: original[field] for field in changed},
            "reference_positive_values": {field: parent[field] for field in changed},
            "synthetic_values": {field: candidate[field] for field in changed},
            "label_status": "Artificial N; experimental failure not established",
        })

    synthetic = [inputs(output[i]) for i in negative_rows]
    matched_masks = sum(row["same_change_mask_as_original"] for row in provenance)
    diagnostics = {
        "seed": seed, "positive_rows_unchanged": len(positive_rows),
        "negative_rows_replaced": len(negative_rows), "positive_rows_dropped": 0,
        "negative_slots_dropped": 0, "original_negative_rows_replaced": len(negative_rows),
        "reference_identity_and_usage_exact": True, "perturbation_counts_exact": True,
        "count_reference": "Selected nearest training-P anchor, not minimum over all positives",
        "field_selection": "Uniform k-element subset of mutable fields; fixed during rejection",
        "donor_sampling": "Empirical training-P frequencies conditional on differing from anchor",
        "null_donors_allowed": True, "training_P_only_donor_values": True,
        "negative_value_or_magnitude_matching": False,
        "rejected_candidates": dict(rejected), "max_candidate_attempts_per_row": max_attempts,
        "relaxations": {}, "same_original_mask_rows": matched_masks,
        "different_original_mask_rows": len(negative_rows) - matched_masks,
        "original_reference_count_histogram": dict(sorted(original_histogram.items())),
        "synthetic_reference_count_histogram": dict(sorted(synthetic_histogram.items())),
        "original_changed_field_counts": {field: original_field_counts[field] for field in FIELDS},
        "synthetic_changed_field_counts": {field: synthetic_field_counts[field] for field in FIELDS},
        "known_training_condition_collisions": len(used & original_keys),
        "holdout_condition_collisions": len(used & holdout_keys),
        "excluded_processed_condition_collisions": len(used & extra_keys),
        "holdout_cluster_collisions": sum(cluster_key(values) in holdout_clusters for values in synthetic),
        "unique_synthetic_negatives": len(used),
        "synthetic_missing_values_by_field": {
            field: sum(values[field] is None for values in synthetic) for field in FIELDS},
    }
    return output, provenance, diagnostics
