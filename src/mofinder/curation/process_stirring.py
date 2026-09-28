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


STIRRING_PARSER_VERSION = "process-stirring-v2"
DETAILED_STIRRING_CLASSES = (
    "Not reported",
    "Static / no stirring",
    "Stirred before static synthesis",
    "Sonicated before static synthesis",
    "Other agitation before static synthesis",
    "Stirred during preparation; later agitation not reported",
    "Sonicated during preparation; later agitation not reported",
    "Other agitation during preparation; later agitation not reported",
    "Stirred during synthesis",
    "Stirred; stage not reported",
    "Sonicated; stage not reported",
    "Shaken / rotated; stage not reported",
    "Other agitation; stage not reported",
    "Unclear / ambiguous",
)
# Fixed from the complete 15,340-record positive reference, before consolidation.
# Apply the same map to negative rows and new input batches. Do not refit it on
# the holdout, on the negative labels, or on each caller's input subset.
RARE_STIRRING_CLASS_COUNTS = {
    "Other agitation before static synthesis": 34,
    "Shaken / rotated; stage not reported": 29,
    "Sonicated; stage not reported": 24,
    "Sonicated during preparation; later agitation not reported": 13,
    "Other agitation; stage not reported": 12,
    "Other agitation during preparation; later agitation not reported": 5,
    "Stirred during synthesis": 4,
}
STIRRING_CLASSES = (
    "Not reported",
    "Static / no stirring",
    "Stirred before static synthesis",
    "Sonicated before static synthesis",
    "Stirred during preparation; later agitation not reported",
    "Stirred; stage not reported",
    "Other reported agitation",
)
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
    r"|premix\w*|initial(?:ly)?|during (?:mixing|dissolution|addition|base addition|gel prep)|to (?:dissolve|mix))\b"
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


def normalize_stirring(value: object) -> dict[str, str]:
    """Return a bounded class plus the matched rule and any review reason.

    The final model class consolidates rare reported agitation and assigns
    unavailable or indeterminate agitation to ``Not reported``. ``detailed_value``
    preserves the original stage-aware class, and ``consolidation_rule`` explains
    every recoding. Nonempty off-schema or contradictory text retains a review
    reason. The full input should be retained by callers as ``stirring_raw``.
    Numerical speeds, times, and intensity adjectives do not establish a stage.
    """
    text = normalize_stirring_text(value)

    def result(label: str, rule: str, reason: str = "") -> dict[str, str]:
        final_label, consolidation = label, ""
        if label in RARE_STIRRING_CLASS_COUNTS:
            final_label = "Other reported agitation"
            consolidation = "positive_reference_class_count_lt_50"
        elif label == "Unclear / ambiguous":
            final_label = "Not reported"
            consolidation = "no_unique_supported_agitation_state"
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
            return result("Other agitation before static synthesis", "other_agitation_and_explicit_static_stage")
        return result("Static / no stirring", "explicit_static_or_no_stirring")

    # A rotation described alongside a prestir is still distinct from stirring.
    if rotated:
        return result("Shaken / rotated; stage not reported", "shaking_rotation_or_vortexing")
    if stirred:
        if _REACTION_STIR.search(text):
            return result("Stirred during synthesis", "explicit_reaction_stage_stirring")
        if _PREP.search(text):
            return result("Stirred during preparation; later agitation not reported", "preparation_stirring_only")
        return result("Stirred; stage not reported", "stirring_without_reaction_stage_evidence")
    if sonic:
        if _PREP.search(text):
            return result("Sonicated during preparation; later agitation not reported", "preparation_sonication_only")
        return result("Sonicated; stage not reported", "sonication_without_reaction_stage_evidence")
    if mixed or re.fullmatch(r"(?:vigorous(?:\s+.+)?|\d+(?:\.\d+)?\s*rpm)", text):
        if _PREP.search(text):
            return result("Other agitation during preparation; later agitation not reported", "preparation_agitation_only")
        return result("Other agitation; stage not reported", "agitation_without_method_or_stage_evidence")
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
    for label, path in (("positive", positive), ("negative", negative)):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        counts[label] = Counter(row["stirring"] for row in source_rows)
        for index, row in enumerate(source_rows, start=1):
            parsed = normalize_stirring(row["stirring"])
            if parsed["review_reason"]:
                review_context.append({
                    "dataset": label, "csv_data_row_1based": index,
                    **{key: row.get(key, "") for key in (
                        "doi", "stirring", "vessel_type", "temperature_c_text",
                        "time_text", "washing_solvent", "activation_text")},
                    **parsed,
                })
    all_counts = counts["positive"] + counts["negative"]
    rows = []
    for raw, count in sorted(all_counts.items(), key=lambda item: (-item[1], item[0])):
        parsed = normalize_stirring(raw)
        rows.append({
            "raw_value": raw,
            "positive_records": counts["positive"][raw],
            "negative_records": counts["negative"][raw],
            "total_records": count,
            "rare_at_most_5_records": count <= 5,
            **parsed,
        })
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
            "distinct_raw_values": len(selected),
        })
    save("stirring_category_counts.csv", category_rows,
         ["category", "positive_records", "negative_records", "total_records", "distinct_raw_values"])
    unresolved_records = sum(row["total_records"] for row in unresolved)
    summary = {
        "positive_records": sum(counts["positive"].values()),
        "negative_records": sum(counts["negative"].values()),
        "distinct_raw_values": len(all_counts),
        "rare_distinct_raw_values": sum(row["rare_at_most_5_records"] for row in rows),
        "unresolved_distinct_raw_values": len(unresolved),
        "unresolved_records": unresolved_records,
    }
    lines = [
        "# Stirring normalization audit", "",
        f"Parser: `{STIRRING_PARSER_VERSION}`. Inputs: `{positive.name}` ({summary['positive_records']:,} records) "
        f"and `{negative.name}` ({summary['negative_records']:,} records).",
        "",
        f"All {len(rows):,} unique extracted strings were enumerated and reviewed by category, "
        f"including {summary['rare_distinct_raw_values']:,} strings occurring in at most five combined records. "
        "The complete mapping, frequencies, normalized text and matching rule are in `stirring_all_raw_values.csv`. "
        "This is a review of extracted text; source publications were not re-read.",
        "",
        "Rules normalize Unicode width, dashes, whitespace and case before classification. "
        "Explicit static synthesis takes priority over initial mixing. The detailed audit retains stirring, sonication "
        "and other initial agitation separately; when both stirring and sonication are specified, the detailed class "
        "records stirring and the raw field retains both. "
        "Preparation followed by heating does not establish static heating. Bare `stirred`, speeds, intensity adjectives "
        "and even `continuous stirring` do not identify the synthesis stage and remain stage-not-reported. "
        "Only explicit reaction-stage wording supports the detailed class `Stirred during synthesis`. "
        "These text classes summarize what is reported; they are not validated measurements of agitation.",
        "",
        "Audit refinements included recognizing `left standing` and `aged without stirring` as static; "
        "retaining rotation despite a separate prestir; handling Unicode range symbols and nonbreaking hyphens; "
        "recognizing `pre-stir/sonication`; retaining unknown later agitation after sealing, heating, reflux or diffusion; "
        "and resolving the rare `vigorous 5 min before heating` as preparation agitation without inventing a stirring mechanism. "
        "Post-cooling stirring does not count as preparation. Reagent addition, reflux, microwave irradiation and "
        "centrifugation alone are not assigned to a synthesis-agitation method.",
        "",
        "## Final class consolidation", "",
        "The seven detailed agitation categories with fewer than 50 positive synthesis records in the fixed "
        "15,340-record reference are merged into `Other reported agitation`. The same fixed mapping is used "
        "for positive and negative rows, future input batches, and model inputs. It is not recalculated per dataset "
        "or split. This broad class asserts that agitation was reported but does not imply a shared method or "
        "stage. `detailed_value`, `consolidation_rule`, the original rule, and raw text retain the specific evidence. "
        "Stage-aware detailed classes remain available for a future sensitivity analysis.", "",
        "| Detailed class merged | Positive reference count |", "|---|---:|",
    ]
    for category, count in RARE_STIRRING_CLASS_COUNTS.items():
        lines.append(f"| {category} | {count} |")
    lines.extend([
        "", "## Final class counts", "",
        "| Class | Positive | Negative | Unique raw strings |",
        "|---|---:|---:|---:|",
    ])
    for row in category_rows:
        lines.append(f"| {row['category']} | {row['positive_records']:,} | {row['negative_records']:,} | {row['distinct_raw_values']:,} |")
    lines.extend([
        "", f"## Agitation not determinable: {unresolved_records:,} records / {len(unresolved)} unique strings", "",
        "The final class is `Not reported` because a unique supported agitation state is unavailable. The detailed "
        "audit retains `Unclear / ambiguous` and an explicit reason, distinguishing these nonempty descriptions "
        "from a blank source field. They are not recoded as static or stirred. Associated vessel, temperature, "
        "duration, washing, and activation fields for every affected row are in `stirring_review_context.csv`.", "",
        "The reference audit inspected all 21 affected positive rows. The 12 centrifugation records from "
        "DOIs `10.1039/c4ta06820c` and `10.1016/j.matchemphys.2022.127039` tie centrifugation to their reported "
        "durations; this is not evidence that centrifugation was necessarily postprocessing, but it still does not "
        "identify a stirring/static state. Three reflux rows specify heating; one microwave row specifies "
        "irradiation; four addition rows specify reagent addition under argon. None supplies a separate agitation "
        "state in the available associated fields. The remaining row says `with or without stirring` and lacks "
        "a unique record-specific choice. The audit does not invent a choice or infer agitation from heating.", "",
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
