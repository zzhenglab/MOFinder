"""Conservative, auditable normalization of extracted agitation descriptions.

The extraction's ``stirring`` field includes sonication, rotation and premixing.
It does not establish that an unqualified ``stirred`` reaction was stirred
continuously or throughout heating.  Categories therefore retain stage
uncertainty, and explicit static growth takes precedence over premixing.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
import re
import unicodedata

from .agitation_source_reviews import SOURCE_REVIEWS


STIRRING_PARSER_VERSION = "process-agitation-v5"
# Detailed methods remain available in the audit after stage-based consolidation.
_METHODS = ("Stirred", "Sonicated", "Shaken", "Rotated", "Vortexed",
            "Homogenized", "Mixed", "Agitated")
_STAGES = (" before static synthesis", " during preparation", " during synthesis",
           "; stage not reported")
STIRRING_LABEL_MAP = {"Static / no stirring": "No stirring", **{
    f"{method}{stage}": f"Agitated{stage}"
    for method in _METHODS if method != "Sonicated" for stage in _STAGES
}}
STIRRING_CLASSES = (
    "No stirring", "Not reported", "Agitated before static synthesis",
    "Agitated during preparation", "Agitated during synthesis",
    "Agitated; stage not reported", "Sonicated before static synthesis",
    "Sonicated during preparation", "Sonicated; stage not reported",
)
DETAILED_STIRRING_CLASSES = ("Not reported", "Static / no stirring") + tuple(
    f"{method}{stage}" for method in _METHODS for stage in _STAGES
) + ("Unclear / ambiguous",)
_MISSING = {
    "", "nan", "none", "null", "<na>", "na", "n/a", "n.a.",
    "not reported", "not specified", "unspecified", "unknown", "nr", "-", "--",
}
_STIR = re.compile(r"\b(?:stir(?:red|ring|rer|rers)?|pre-?stir(?:red|ring)?|magnetic agitation)\b")
_SONIC = re.compile(r"\b(?:ultraso\w*|sonicat\w*)\b")
_ROTATE = re.compile(r"\b(?:shak\w*|shook|rotat\w*|rpb|vortex\w*)\b")
_MIX = re.compile(r"\b(?:mix(?:ed|ing)?|premix(?:ed|ing)?|pre-mix(?:ed|ing)?|agitat\w*|homogeniz\w*|homogenis\w*)\b")
_NO_STIR = re.compile(r"\b(?:without|no|not)\s+(?:any\s+)?(?:stir(?:red|ring)?|agitat\w*|rotation)\b")
_STATIC = re.compile(r"\b(?:static|undisturbed|left standing|allowed to stand)\b")
_PREP = re.compile(
    r"\b(?:pre-?(?:mix\w*|stir\w*|heat\w*|reaction|seal\w*|treatment|dissolution|dispersion|aging)"
    r"|premix\w*|initial(?:ly)?|during (?:preparation|mixing|dissolution|addition|base addition|gel prep)|to (?:dissolve|mix))\b"
    r"|\b(?:before|prior to)\b"
    r"|\bthen\s+(?:(?:sealed|capped)\s+(?:and\s+)?)?(?:heat\w*|reflux\w*|age\w*|layer\w*|seal\w*|incubat\w*|micro\w*|kept|held|solvent evaporation)\b"
    r"|;\s*(?:layered slow diffusion|refluxed)\b|\buntil dissolved\b"
    r"|\b(?:pre|premix)\s*\)"
)
_REACTION_STIR = re.compile(
    r"\b(?:during|throughout)\s+(?:the\s+)?(?:reaction|synthesis|conversion|heating|reflux|crystallization|crystallisation)\b"
    r"|\bunder reflux\b|\bstirred\s*\(reflux\)"
    r"|\bmaintained to end\b"
)


def normalize_stirring_text(value: object) -> str:
    """Normalize typography without interpreting chemistry or changing raw data."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.translate(str.maketrans({
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2212": "-", "\u00a0": " ", "_": " ",
    }))
    text = re.sub(r"\s*-\s*", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def method_name(text: str, rotation_first: bool = False) -> str:
    """Name a reported method without converting speed/intensity into a method."""
    if rotation_first:
        if re.search(r"\b(?:shak\w*|shook)\b", text):
            return "Shaken"
        if re.search(r"\bvortex\w*\b", text):
            return "Vortexed"
        if re.search(r"\b(?:rotat\w*|rpb)\b", text):
            return "Rotated"
    if _STIR.search(text):
        return "Stirred"
    if _SONIC.search(text):
        return "Sonicated"
    if re.search(r"\bhomogeni[sz]\w*\b", text):
        return "Homogenized"
    if re.search(r"\b(?:mix(?:ed|ing)?|premix(?:ed|ing)?|pre-mix(?:ed|ing)?)\b", text):
        return "Mixed"
    if re.search(r"\bagitat\w*\b", text):
        return "Agitated"
    return ""


def normalize_stirring(value: object, doi: str = "") -> dict[str, str]:
    """Return a bounded class plus the matched rule and any review reason.

    The final model class combines non-sonication methods by their reported
    stage. Detailed methods remain in the audit. Unavailable or indeterminate
    agitation is ``Not reported``.
    ``detailed_value`` and ``consolidation_rule`` explain every recoding. Nonempty off-schema or contradictory text retains a review
    reason. The full input should be retained by callers as ``stirring_raw``.
    Numerical speeds, times, and intensity adjectives do not establish a stage.
    """
    text = normalize_stirring_text(value)
    normalized_doi = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/|^doi\s*:\s*", "", str(doi).strip().casefold())
    review = next((item for item in SOURCE_REVIEWS
                   if item['doi'] == normalized_doi
                   and normalize_stirring_text(item['raw_value']) == text), None)
    if review:
        parsed = normalize_stirring(review['corrected_text'])
        parsed['normalized_text'] = text
        parsed['rule'] = 'source_review:' + normalized_doi + ':' + parsed['rule']
        parsed['consolidation_rule'] = ';'.join(filter(None, (
            'source_verified_method_stage', parsed['consolidation_rule'])))
        return parsed

    def result(label: str, rule: str, reason: str = "") -> dict[str, str]:
        final_label, consolidation = label, ""
        if label == "Unclear / ambiguous":
            final_label = "Not reported"
            consolidation = "no_unique_supported_agitation_state"
        elif label in STIRRING_LABEL_MAP:
            final_label = STIRRING_LABEL_MAP[label]
            if label == "Static / no stirring":
                consolidation = "shorten_agitation_label"
            elif final_label != label:
                consolidation = "merge_nonsonication_methods_by_stage"
        if final_label not in STIRRING_CLASSES:
            raise ValueError(
                f"Agitation state {label!r} is outside the nine-class schema; "
                "review the class mapping before processing this new state."
            )
        return {"value": final_label, "detailed_value": label,
                "consolidation_rule": consolidation, "rule": rule,
                "normalized_text": text, "review_reason": reason}

    if text in _MISSING:
        return result("Not reported", "missing")
    if re.search(r"\b(?:with or without|with/without|stirred or static|static or stirred)\b", text):
        return result("Unclear / ambiguous", "alternative_agitation_states",
                      "The extraction lists alternative agitation states, not a unique record-specific state.")
    if re.search(r"\b(?:not|non)[ -]?static\b", text):
        return result("Unclear / ambiguous", "negated_static",
                      "Negated static wording does not identify the agitation method or stage.")

    # Remove a negative phrase before detecting positive evidence of stirring.
    # Post-cooling agitation cannot be used as evidence of synthesis premixing.
    positive_text = _NO_STIR.sub("", text)
    positive_text = re.sub(r"\bstirr\w*\s+after cooling\b", "", positive_text)
    stirred = bool(_STIR.search(positive_text))
    sonic = bool(_SONIC.search(positive_text))
    rotated = bool(_ROTATE.search(positive_text))
    mixed = bool(_MIX.search(positive_text))
    static = bool(_STATIC.search(text) or _NO_STIR.search(text))
    if static:
        if re.search(r"\bstatic\b[^;]*\bthen\s+stirr\w*", text):
            return result("Unclear / ambiguous", "static_followed_by_stirring",
                          "Static precedes stirring; the synthesis-stage state cannot be assigned conservatively.")
        if stirred:
            return result("Stirred before static synthesis", "stirring_and_explicit_static_stage")
        if sonic:
            return result("Sonicated before static synthesis", "sonication_and_explicit_static_stage")
        if rotated or mixed:
            method = method_name(positive_text, rotation_first=True)
            return result(f"{method} before static synthesis", "method_and_explicit_static_stage")
        return result("Static / no stirring", "explicit_static_or_no_stirring")

    # A distinct rotation alongside a prestir is retained as the main method.
    method = method_name(positive_text, rotation_first=True)
    if method:
        if _REACTION_STIR.search(text):
            return result(f"{method} during synthesis", "explicit_reaction_stage_agitation")
        # Preparation wording associated only with a separate prestir cannot
        # establish that the rotation also occurred during preparation.
        if _PREP.search(text) and not (rotated and stirred):
            return result(f"{method} during preparation", "explicit_preparation_agitation")
        return result(f"{method}; stage not reported", "method_without_reaction_stage_evidence")
    if re.search(r"\bcentrifug\w*\b", text):
        reason = "Centrifugation alone does not establish a stirring or static state; its stage is not inferred."
    elif re.search(r"\b(?:reflux\w*|microwave\w*)\b", text):
        reason = "Heating or irradiation alone does not specify agitation."
    elif "addition" in text:
        reason = "Reagent addition alone does not specify agitation."
    else:
        reason = "No supported agitation method or explicit static state was found."
    return result("Unclear / ambiguous", "unresolved_nonempty_description", reason)


def write_stirring_audit(positive: Path, negative: Path, output: Path) -> dict[str, int]:
    """Export every distinct input phrase, class counts, and unresolved phrases.

    This audits extracted text rather than verifying the source publications.
    No source tables are modified.  Rare means at most five combined records.
    """
    counts: dict[str, Counter[str]] = {}
    review_context = []
    grouped = {}
    for label, path in (("positive", positive), ("negative", negative)):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        counts[label] = Counter(row["stirring"] for row in source_rows)
        for index, row in enumerate(source_rows, start=1):
            parsed = normalize_stirring(row["stirring"], row.get("doi", ""))
            key = (row["stirring"], *parsed.values())
            if key not in grouped:
                grouped[key] = {"raw_value": row["stirring"], "positive_records": 0,
                                "negative_records": 0, **parsed}
            grouped[key][label + "_records"] += 1
            if parsed["review_reason"] or parsed['rule'].startswith('source_review:'):
                review_context.append({
                    "dataset": label, "csv_data_row_1based": index,
                    **{key: row.get(key, "") for key in (
                        "doi", "stirring", "vessel_type", "temperature_c_text",
                        "time_text", "washing_solvent", "activation_text")},
                    **parsed,
                })
    all_counts = counts["positive"] + counts["negative"]
    rows = []
    for item in grouped.values():
        count = item['positive_records'] + item['negative_records']
        rows.append({**item, "total_records": count,
                     "rare_at_most_5_records": all_counts[item['raw_value']] <= 5})
    rows.sort(key=lambda item: (-item['total_records'], item['raw_value'], item['rule']))
    output.mkdir(parents=True, exist_ok=True)

    def save(name: str, records: list[dict], fieldnames: list[str]) -> None:
        with (output / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    headers = ["raw_value", "positive_records", "negative_records", "total_records",
               "rare_at_most_5_records", "value", "detailed_value", "consolidation_rule",
               "rule", "normalized_text", "review_reason"]
    save("stirring_all_raw_values.csv", rows, headers)
    unresolved = [row for row in rows if row["review_reason"]]
    save("stirring_unresolved_values.csv", unresolved, headers)
    context_headers = ["dataset", "csv_data_row_1based", "doi", "stirring", "vessel_type",
                       "temperature_c_text", "time_text", "washing_solvent", "activation_text",
                       "value", "detailed_value", "consolidation_rule", "rule", "normalized_text",
                       "review_reason"]
    save("stirring_review_context.csv", review_context, context_headers)
    category_rows = []
    for category in STIRRING_CLASSES:
        selected = [row for row in rows if row["value"] == category]
        category_rows.append({
            "category": category,
            "positive_records": sum(row["positive_records"] for row in selected),
            "negative_records": sum(row["negative_records"] for row in selected),
            "total_records": sum(row["total_records"] for row in selected),
            "distinct_raw_values": len({item["raw_value"] for item in selected}),
        })
    save("stirring_category_counts.csv", category_rows,
         ["category", "positive_records", "negative_records", "total_records", "distinct_raw_values"])
    unresolved_records = sum(row["total_records"] for row in unresolved)
    summary = {
        "positive_records": sum(counts["positive"].values()),
        "negative_records": sum(counts["negative"].values()),
        "distinct_raw_values": len(all_counts),
        "rare_distinct_raw_values": sum(n <= 5 for n in all_counts.values()),
        "unresolved_distinct_raw_values": len({row["raw_value"] for row in unresolved}),
        "unresolved_records": unresolved_records,
    }
    lines = [
        "# Agitation normalization audit", "",
        f"Parser: `{STIRRING_PARSER_VERSION}`. Model field: `agitation`; source field: `stirring`.", "",
        f"Enumerated all {len(all_counts):,} unique extracted strings across "
        f"{summary['positive_records']:,} positive and {summary['negative_records']:,} negative records. "
        "See `stirring_all_raw_values.csv` for exact raw text and matched rules. "
        "These filenames refer to the original extraction column.", "",
        "Nine final classes consolidate non-sonication methods by reported stage, while retaining the three "
        "observed sonication stages separately. Final labels contain two to five words. Every original method "
        "and stage remains in `detailed_value`, alongside the raw text and consolidation rule. No frequency "
        "threshold determines these classes. A newly observed supported state outside this nine-class schema "
        "raises an error requiring class-map review; it is not silently recoded as missing. Preparation does not "
        "establish agitation during later heating; "
        "unqualified stirring does not establish continuous synthesis stirring. Explicit static synthesis takes "
        "precedence over preparation. When both initial stirring and sonication are named, stirring is the primary "
        "detailed label and raw text retains both. Rotation is retained in the detailed label when a separate "
        "prestir is reported. Final `Agitated` classes combine stirring, shaking, rotation, vortexing, "
        "homogenization, mixing, and agitation without a specified method; they preserve the reported stage. "
        "Bare speeds or intensity adjectives do not establish a method. Heating, centrifugation, and reagent "
        "addition alone do not establish synthesis agitation. Missing or unresolved descriptions use `Not reported`; "
        "unresolved nonempty text remains distinguished by its audit reason.", "",
        "The same deterministic rules apply to positive and negative records before JSONL preparation. "
        "The original eight model inputs, labels, split assignments, and row order remain unchanged.", "",
        "## Final class counts", "",
        "| Class | Positive | Negative | Unique raw strings |",
        "|---|---:|---:|---:|",
    ]
    for row in category_rows:
        if row['total_records']:
            lines.append(f"| {row['category']} | {row['positive_records']:,} | {row['negative_records']:,} | {row['distinct_raw_values']:,} |")
    lines.extend([
        "", f"## Unresolved descriptions: {unresolved_records:,} records / {len(unresolved)} strings", "",
        "Associated tabular context is retained in `stirring_review_context.csv`. Targeted publication checks "
        "are documented separately; this is not a full source-publication verification.", "",
        "| Raw string | Positive | Negative | Reason |", "|---|---:|---:|---|",
    ])
    for row in unresolved:
        lines.append(f"| {row['raw_value']} | {row['positive_records']} | {row['negative_records']} | {row['review_reason']} |")
    (output / "stirring_audit_notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Audit normalization of all extracted stirring descriptions.")
    parser.add_argument("--positive", type=Path, default=Path("data/processed_data/processed_positive.csv"))
    parser.add_argument("--negative", type=Path, default=Path("data/processed_data/processed_negative.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed_data/with_process_details/audit"))
    args = parser.parse_args()
    print(json.dumps(write_stirring_audit(args.positive, args.negative, args.output), indent=2))
