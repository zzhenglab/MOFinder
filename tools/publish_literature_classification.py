"""Publish validated rough topic labels without changing retrieval identities.

The input is the completed literature-triage ``full_decision_audit.csv``. This
exporter does not classify papers or generate/modify the saved triage decisions.
"""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re


CATEGORIES = (
    "Chemical synthesis", "Theory & modeling", "Crystal engineering",
    "Functional materials",
)
INVENTORY_FIELDS = ["DOI", "Publisher", "DOI Link", "Classification"]
TAXONOMY_POLICY = "synthesis-inclusive-v1"
AUDIT_FIELDS = {
    "DOI": "doi_key",
    "Classification": "category",
    "Triage decision": "triage_decision",
    "Document Type": "Document Type",
    "Bibliography row": "excel_row",
    "Classification method": "classification_method",
    "Taxonomy policy": "taxonomy_policy",
    "Classification reason": "classification_reason",
    "Primary topic category (v4)": "primary_topic_category",
    "Primary topic evidence": "primary_topic_evidence",
    "Framework synthesis reported": "has_framework_synthesis",
    "Framework synthesis evidence": "framework_synthesis_evidence",
    "Taxonomy reassigned": "taxonomy_reassigned",
    "Reassignment reason": "reassignment_reason",
    "Review needed": "review_needed",
    "Low confidence": "low_confidence",
    "Fallback used": "fallback_used",
    "Fallback basis": "fallback_basis",
    "Review reason": "review_reason",
    "Evidence": "evidence",
    "Primary topic reason": "primary_topic_reason",
    "Classifier version": "classifier_version",
}


def normalize_doi(value):
    value = value.strip().lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def publish(audit_path, repo_root, *, analysis_manifest=None, classifier=None):
    """Validate every join before replacing the public tables and manifests."""
    audit_path, repo_root = Path(audit_path), Path(repo_root)
    folder = repo_root / "data/metadata/literature_retrieval"
    fields, rows = read_csv(audit_path)
    missing = (set(AUDIT_FIELDS.values()) | {"DOI"}) - set(fields)
    if missing:
        raise ValueError(f"Missing audit fields: {sorted(missing)}")
    by_doi = {}
    for row in rows:
        doi = normalize_doi(row["doi_key"])
        if not doi.startswith("10.") or "/" not in doi:
            raise ValueError(f"Invalid DOI key: {doi!r}")
        if doi in by_doi:
            raise ValueError(f"Duplicate audit DOI: {doi}")
        if normalize_doi(row["DOI"]) != doi:
            raise ValueError(f"DOI/key mismatch: {doi}")
        if row["category"] not in CATEGORIES:
            raise ValueError(f"Unresolved/unknown topic for {doi}: {row['category']!r}")
        if row["triage_decision"] not in {"Y", "N"}:
            raise ValueError(f"Unresolved triage decision: {doi}")
        for flag in ("review_needed", "low_confidence", "fallback_used",
                     "has_framework_synthesis", "taxonomy_reassigned"):
            if row[flag] not in {"True", "False"}:
                raise ValueError(f"Invalid {flag} flag: {doi}")
        if row["fallback_used"] == "True" and not row["fallback_basis"]:
            raise ValueError(f"Missing fallback provenance: {doi}")
        if row["classification_method"] != "topic rules":
            raise ValueError(f"Pure rule-generated publication does not accept overrides: {doi}")
        if not row["classifier_version"]:
            raise ValueError(f"Missing classification provenance: {doi}")
        if row["taxonomy_policy"] != TAXONOMY_POLICY:
            raise ValueError(f"Unknown taxonomy policy: {doi}")
        if row["primary_topic_category"] not in CATEGORIES:
            raise ValueError(f"Unresolved/unknown primary topic: {doi}")
        reassigned = row["category"] != row["primary_topic_category"]
        if (row["taxonomy_reassigned"] == "True") != reassigned:
            raise ValueError(f"Inconsistent taxonomy reassignment flag: {doi}")
        if reassigned and (row["category"] != "Chemical synthesis"
                           or row["has_framework_synthesis"] != "True"
                           or not row["reassignment_reason"]):
            raise ValueError(f"Unsupported taxonomy reassignment: {doi}")
        if row["has_framework_synthesis"] == "True" and not row["framework_synthesis_evidence"]:
            raise ValueError(f"Missing framework synthesis evidence: {doi}")
        if not row["classification_reason"]:
            raise ValueError(f"Missing classification reason: {doi}")
        by_doi[doi] = {**row, "doi_key": doi}

    prior_audit_path = folder / "classification_audit.csv"
    if prior_audit_path.exists():
        _, prior_rows = read_csv(prior_audit_path)
        prior_by_doi = {normalize_doi(row["DOI"]): row for row in prior_rows}
        if set(prior_by_doi) != set(by_doi):
            raise ValueError("Published and incoming audits must cover the same DOI identities.")
        for doi, row in by_doi.items():
            prior = prior_by_doi[doi]
            primary_topic = prior.get("Primary topic category (v4)", prior["Classification"])
            if row["primary_topic_category"] != primary_topic:
                raise ValueError(f"Historical primary topic changed: {doi}")
            if row["triage_decision"] != prior["Triage decision"]:
                raise ValueError(f"Historical triage decision changed: {doi}")
    _, bibliography = read_csv(repo_root / "data/metadata/literature_metadata.csv")
    bibliography_dois = {normalize_doi(row["DOI"]) for row in bibliography}
    if set(by_doi) != bibliography_dois:
        raise ValueError("Audit must cover exactly the bibliography's normalized unique DOIs.")
    for doi, row in by_doi.items():
        try:
            position = int(row["excel_row"]) - 2
        except ValueError as error:
            raise ValueError(f"Invalid bibliography row: {doi}") from error
        if not 0 <= position < len(bibliography) or normalize_doi(bibliography[position]["DOI"]) != doi:
            raise ValueError(f"Bibliography row does not match DOI: {doi}")

    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parent_path = repo_root / "data/manifest.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    old_exports = {entry["file"]: entry for entry in manifest["exports"]}
    outputs, exports = {}, []
    selected_dois = {doi for doi, row in by_doi.items() if row["triage_decision"] == "Y"}
    for name in ("papers.csv", "supporting_information.csv"):
        source_fields, inventory = read_csv(folder / name)
        if not {"DOI", "Publisher", "DOI Link"}.issubset(source_fields):
            raise ValueError(f"Missing retrieval identity fields: {name}")
        if {normalize_doi(row["DOI"]) for row in inventory} != selected_dois:
            raise ValueError(f"Retrieval inventory must match the saved Y decisions: {name}")
        converted = [{**{key: row[key] for key in INVENTORY_FIELDS[:-1]},
                      "Classification": by_doi[normalize_doi(row["DOI"])]["category"]}
                     for row in inventory]
        content = csv_bytes(INVENTORY_FIELDS, converted)
        outputs[folder / name] = content
        entry = dict(old_exports[name])
        entry.pop("status_counts", None)
        entry.update(sha256=digest(content), row_count=len(converted), columns=INVENTORY_FIELDS,
                     classification_counts=dict(sorted(Counter(row["Classification"] for row in converted).items())))
        exports.append(entry)

    ordered = [by_doi[doi] for doi in sorted(by_doi)]
    compact = [{"DOI": row["doi_key"], "Classification": row["category"]} for row in ordered]
    audit = [{label: row[field] for label, field in AUDIT_FIELDS.items()} for row in ordered]
    for name, columns, records in (
        ("doi_classification.csv", ["DOI", "Classification"], compact),
        ("classification_audit.csv", list(AUDIT_FIELDS), audit),
    ):
        content = csv_bytes(columns, records)
        outputs[folder / name] = content
        exports.append({"file": name, "sha256": digest(content), "row_count": len(records),
                        "unique_doi_count": len(records), "columns": columns,
                        "source_id": "literature_topic_classification_audit",
                        "source_sha256": digest(audit_path.read_bytes())})

    summary = [{"Category": category,
                "Before triage": sum(row["category"] == category for row in ordered),
                "After triage (Y)": sum(row["category"] == category and row["triage_decision"] == "Y" for row in ordered),
                "After triage (N)": sum(row["category"] == category and row["triage_decision"] == "N" for row in ordered)}
               for category in CATEGORIES]
    provenance = {
        "source_id": "literature_topic_classification_audit",
        "source_sha256": digest(audit_path.read_bytes()),
        "bibliography_sha256": digest((repo_root / "data/metadata/literature_metadata.csv").read_bytes()),
        "classifier_versions": sorted({row["classifier_version"] for row in ordered}),
        "generated_by_llm": False,
        "validated_against_expert_topic_labels": False,
        "method": "Deterministic rough title/abstract/document-type rules with synthesis-inclusive grouping; prior primary topics and uncertainty flags retained.",
        "taxonomy_policy": TAXONOMY_POLICY,
        "chemical_synthesis_definition": "Includes original papers reporting experimental MOF/framework preparation, even when structure or application is the main topic.",
        "taxonomy_change_interpretation": "A descriptive category-definition change; does not establish improved screening accuracy.",
        "primary_topic_classifier_version": "4.0.0",
        "previous_publication": "https://github.com/zzhenglab/MOFinder/tree/76738b0/data/metadata/literature_retrieval",
        "triage_decisions": "Existing saved model Y/N decisions, joined separately; not used to assign topics.",
        "canonical_record": "Longest title/abstract representative; Bibliography row identifies its original workbook row (header is row 1).",
        "unique_dois": len(ordered),
        "triage_counts": dict(sorted(Counter(row["triage_decision"] for row in ordered).items())),
        "review_needed_count": sum(row["review_needed"] == "True" for row in ordered),
        "low_confidence_count": sum(row["low_confidence"] == "True" for row in ordered),
        "fallback_count": sum(row["fallback_used"] == "True" for row in ordered),
        "manual_overrides_applied": 0,
        "unclassified_count": 0,
        "framework_synthesis_reported_count": sum(row["has_framework_synthesis"] == "True" for row in ordered),
        "taxonomy_reassigned_count": sum(row["taxonomy_reassigned"] == "True" for row in ordered),
        "primary_topic_counts": dict(sorted(Counter(row["primary_topic_category"] for row in ordered).items())),
        "topic_summary": summary,
    }
    if analysis_manifest is not None:
        source_manifest = json.loads(Path(analysis_manifest).read_text(encoding="utf-8"))
        if source_manifest.get("classifier_uses_triage_decisions") is not False:
            raise ValueError("Analysis manifest must confirm topics do not use triage decisions.")
        if source_manifest.get("manual_overrides_applied") != 0:
            raise ValueError("Pure rule-generated publication requires zero manual overrides.")
        if source_manifest.get("taxonomy_policy") != TAXONOMY_POLICY:
            raise ValueError("Analysis manifest must record the synthesis-inclusive taxonomy policy.")
        provenance["analysis_manifest_sha256"] = digest(Path(analysis_manifest).read_bytes())
        input_hashes = source_manifest.get("inputs", {})
        provenance["input_sha256"] = sorted(set(input_hashes.values()))
        if source_manifest.get("YN_source") in input_hashes:
            provenance["triage_decision_source_sha256"] = input_hashes[source_manifest["YN_source"]]
        provenance["triage_decision_column"] = source_manifest.get("YN_column")
    if classifier is not None:
        classifier_path = Path(classifier).resolve()
        provenance["classifier_path"] = classifier_path.relative_to(repo_root.resolve()).as_posix()
        provenance["classifier_sha256"] = digest(classifier_path.read_bytes())
    manifest.update(schema_version=3, exports=exports, classification=provenance, transformations=[
        "Preserve retrieval DOI, publisher identifiers, DOI links, duplicate rows, and original row order.",
        "Remove Downloaded and SI Downloaded columns from published inventories.",
        "Join rough topic Classification by normalized DOI; preserve all saved triage decisions.",
        "Export one normalized DOI per row for the full bibliography, sorted by DOI.",
        "Keep assignment evidence, review flags, document type, and canonical source row in classification_audit.csv.",
        "Preserve v4 primary-contribution labels and saved Y/N; publish synthesis-inclusive categories with matched framework-preparation evidence.",
    ])
    outputs[manifest_path] = json_bytes(manifest)
    new_entries = []
    for entry in exports[2:]:
        new_entries.append({"path": "data/metadata/literature_retrieval/" + entry["file"],
                            "source_id": entry["source_id"], "source_sha256": entry["source_sha256"],
                            "export_sha256": entry["sha256"], "rows": entry["row_count"],
                            "columns": entry["columns"],
                            "provenance_manifest": "data/metadata/literature_retrieval/manifest.json"})
    replaced = {entry["path"] for entry in new_entries}
    parent["files"] = [entry for entry in parent["files"] if entry["path"] not in replaced] + new_entries
    outputs[parent_path] = json_bytes(parent)
    # All identities, coverage, and provenance are checked before the first write.
    for path, content in outputs.items():
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path, help="Final full_decision_audit.csv")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--analysis-manifest", type=Path)
    parser.add_argument("--classifier", type=Path, help="Public classifier source inside the repository")
    args = parser.parse_args()
    print(json.dumps(publish(args.audit, args.repo_root, analysis_manifest=args.analysis_manifest,
                             classifier=args.classifier), indent=2))


if __name__ == "__main__":
    main()
