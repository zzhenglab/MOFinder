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


STIRRING_PARSER_VERSION = "process-stirring-v1"
STIRRING_CLASSES = (
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

    Missing and unresolved are different: nonempty off-schema or contradictory
    descriptions stay ``Unclear / ambiguous`` and carry a reason.  The full
    input should be retained by callers as ``stirring_raw``.  Numerical speeds,
    times, and intensity adjectives are deliberately not used to infer a stage.
    """
    text = normalize_stirring_text(value)

    def result(label: str, rule: str, reason: str = "") -> dict[str, str]:
        return {"value": label, "rule": rule, "normalized_text": text, "review_reason": reason}

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
        reason = "Centrifugation alone is not evidence of synthesis-stage stirring."
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
    for label, path in (("positive", positive), ("negative", negative)):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            counts[label] = Counter(row["stirring"] for row in csv.DictReader(handle))
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
               "rare_at_most_5_records", "value", "rule", "normalized_text", "review_reason"]
    save("stirring_all_raw_values.csv", rows, headers)
    unresolved = [row for row in rows if row["review_reason"]]
    save("stirring_unresolved_values.csv", unresolved, headers)
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
        "Explicit static synthesis takes priority over initial mixing. Stirring, sonication and other initial agitation "
        "remain separate; when both stirring and sonication are specified, the class records stirring and the raw field retains both. "
        "Preparation followed by heating does not establish static heating. Bare `stirred`, speeds, intensity adjectives "
        "and even `continuous stirring` do not identify the synthesis stage and remain stage-not-reported. "
        "Only explicit reaction-stage wording supports `Stirred during synthesis`. "
        "These text classes summarize what is reported; they are not validated measurements of agitation.",
        "",
        "Audit refinements included recognizing `left standing` and `aged without stirring` as static; "
        "retaining rotation despite a separate prestir; handling Unicode range symbols and nonbreaking hyphens; "
        "recognizing `pre-stir/sonication`; retaining unknown later agitation after sealing, heating, reflux or diffusion; "
        "and resolving the rare `vigorous 5 min before heating` as preparation agitation without inventing a stirring mechanism. "
        "Post-cooling stirring does not count as preparation. Reagent addition, reflux, microwave irradiation and "
        "centrifugation alone are not assigned to a synthesis-agitation method.",
        "",
        "| Class | Positive | Negative | Unique raw strings |",
        "|---|---:|---:|---:|",
    ]
    for row in category_rows:
        lines.append(f"| {row['category']} | {row['positive_records']:,} | {row['negative_records']:,} | {row['distinct_raw_values']:,} |")
    lines.extend([
        "", f"## Residual ambiguity: {unresolved_records:,} records / {len(unresolved)} unique strings", "",
        "These remain `Unclear / ambiguous`, distinct from `Not reported`, with an explicit review reason. "
        "Do not silently recode these phrases as static, stirred, or missing.", "",
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
