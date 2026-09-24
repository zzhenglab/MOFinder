"""Check DOI joins and failure-before-write guarantees of topic publication."""

import importlib.util
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "classification_export", ROOT / "tools/publish_literature_classification.py")
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class ClassificationPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "data/metadata/literature_retrieval"
        self.folder.mkdir(parents=True)
        bibliography = [{"DOI": "10.1234/YES"}, {"DOI": "10.1234/no"}, {"DOI": "10.1234/YES"}]
        (self.folder.parent / "literature_metadata.csv").write_bytes(export.csv_bytes(["DOI"], bibliography))
        inventory = [{"DOI": "10.1234/YES", "Publisher": "publisher_A", "DOI Link": "https://doi.org/10.1234/YES",
                      "Downloaded": "1", "SI Downloaded": "0"}] * 2
        for name in ("papers.csv", "supporting_information.csv"):
            (self.folder / name).write_bytes(export.csv_bytes(list(inventory[0]), inventory))
        self.manifest = {"schema_version": 1, "exports": [
            {"file": name, "source_sha256": "source-workbook-hash", "status_counts": {"Downloaded": {"1": 2}}}
            for name in ("papers.csv", "supporting_information.csv")]}
        self.manifest["exports"].extend({"file": name} for name in
                                        ("doi_classification.csv", "classification_audit.csv"))
        (self.folder / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "data/manifest.json").write_text(json.dumps({"files": [
            {"path": "unchanged"},
            {"path": "data/metadata/literature_retrieval/doi_classification.csv"},
            {"path": "data/metadata/literature_retrieval/classification_audit.csv"},
        ]}), encoding="utf-8")
        self.audit_path = self.root / "full_decision_audit.csv"
        self.audit = [{"DOI": doi, "doi_key": doi, "category": category, "triage_decision": decision,
                       "Document Type": "Article", "excel_row": row, "classification_method": "topic rules",
                       "review_needed": "True", "review_reason": "Weak evidence", "evidence": "title phrase",
                       "low_confidence": "True", "fallback_used": "True", "fallback_basis": "lexical evidence",
                       "taxonomy_policy": export.TAXONOMY_POLICY,
                       "classification_reason": "Synthesis-inclusive grouping" if decision == "Y" else "Primary topic retained",
                       "primary_topic_category": "Crystal engineering" if decision == "Y" else category,
                       "primary_topic_evidence": "original primary-topic evidence",
                       "has_framework_synthesis": "True" if decision == "Y" else "False",
                       "framework_synthesis_evidence": "Two coordination frameworks were synthesized." if decision == "Y" else "",
                       "taxonomy_reassigned": "True" if decision == "Y" else "False",
                       "reassignment_reason": "Reported framework preparation" if decision == "Y" else "",
                       "primary_topic_reason": "Primary contribution", "classifier_version": "test"}
                      for doi, category, decision, row in (("10.1234/yes", "Chemical synthesis", "Y", "4"),
                                                           ("10.1234/no", "Functional materials", "N", "3"))]
        self.write_audit()

    def write_audit(self):
        self.audit_path.write_bytes(export.csv_bytes(list(self.audit[0]), self.audit))

    def test_publication_preserves_duplicate_identity_and_uncertainty(self):
        result = export.publish(self.audit_path, self.root)
        self.assertEqual(result["triage_counts"], {"N": 1, "Y": 1})
        self.assertEqual(result["review_needed_count"], 2)
        self.assertEqual(result["fallback_count"], 2)
        self.assertEqual(result["taxonomy_reassigned_count"], 1)
        self.assertEqual(result["taxonomy_policy"], export.TAXONOMY_POLICY)
        for name in ("papers.csv", "supporting_information.csv"):
            fields, rows = export.read_csv(self.folder / name)
            self.assertEqual(fields, export.INVENTORY_FIELDS)
            self.assertEqual([row["DOI"] for row in rows], ["10.1234/YES"] * 2)
            self.assertEqual([row["Classification"] for row in rows], ["Chemical synthesis"] * 2)
        self.assertEqual({path.name for path in self.folder.iterdir()},
                         {"papers.csv", "supporting_information.csv", "manifest.json"})
        manifest = json.loads((self.folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["file"] for entry in manifest["exports"]],
                         ["papers.csv", "supporting_information.csv"])
        parent = json.loads((self.root / "data/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(parent["files"], [{"path": "unchanged"}])
        self.assertEqual(result["source_sha256"], export.digest(self.audit_path.read_bytes()))
        before = {path: path.read_bytes() for path in self.folder.iterdir()}
        export.publish(self.audit_path, self.root)
        self.assertEqual(before, {path: path.read_bytes() for path in self.folder.iterdir()})

    def test_invalid_audit_does_not_modify_publication(self):
        before = {path: path.read_bytes() for path in self.folder.iterdir()}
        original = [dict(row) for row in self.audit]
        for problem in ("missing_doi", "duplicate_doi", "unclassified", "wrong_decision",
                        "wrong_source_row", "manual_override", "missing_synthesis_evidence",
                        "wrong_reassignment_flag", "wrong_policy", "unsupported_reassignment"):
            with self.subTest(problem=problem):
                self.audit = [dict(row) for row in original]
                if problem == "missing_doi":
                    self.audit.pop()
                elif problem == "duplicate_doi":
                    self.audit.append(dict(self.audit[0]))
                elif problem == "unclassified":
                    self.audit[0]["category"] = "Unclassified"
                elif problem == "wrong_decision":
                    self.audit[0]["triage_decision"] = "N"
                elif problem == "manual_override":
                    self.audit[0]["classification_method"] = "manual override"
                elif problem == "missing_synthesis_evidence":
                    self.audit[0]["framework_synthesis_evidence"] = ""
                elif problem == "wrong_reassignment_flag":
                    self.audit[0]["taxonomy_reassigned"] = "False"
                elif problem == "wrong_policy":
                    self.audit[0]["taxonomy_policy"] = "unrecorded-policy"
                elif problem == "unsupported_reassignment":
                    self.audit[0]["category"] = "Functional materials"
                else:
                    self.audit[0]["excel_row"] = "3"
                self.write_audit()
                with self.assertRaises(ValueError):
                    export.publish(self.audit_path, self.root)
                self.assertEqual(before, {path: path.read_bytes() for path in self.folder.iterdir()})

class PublishedClassificationIntegrityTests(unittest.TestCase):
    def test_public_tables_match_each_other_and_recorded_provenance(self):
        folder = ROOT / "data/metadata/literature_retrieval"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["file"] for entry in manifest["exports"]],
                         ["papers.csv", "supporting_information.csv"])
        provenance = manifest["classification"]
        by_inventory = {}
        for entry in manifest["exports"]:
            path = folder / entry["file"]
            self.assertEqual(export.digest(path.read_bytes()), entry["sha256"], path.name)
            fields, rows = export.read_csv(path)
            self.assertEqual(fields, entry["columns"], path.name)
            self.assertEqual(len(rows), entry["row_count"], path.name)
            self.assertEqual(fields, export.INVENTORY_FIELDS)
            self.assertEqual(len(rows), 7437)
            self.assertTrue(all(row["Classification"] in export.CATEGORIES for row in rows))
            self.assertEqual(Counter(row["Classification"] for row in rows), entry["classification_counts"])
            by_doi = {export.normalize_doi(row["DOI"]): row["Classification"] for row in rows}
            self.assertEqual(len(by_doi), entry["unique_doi_count"])
            self.assertEqual(len(by_doi), provenance["triage_counts"]["Y"])
            self.assertTrue(all(row["Classification"] == by_doi[export.normalize_doi(row["DOI"])]
                                for row in rows))
            self.assertEqual(Counter(by_doi.values()),
                             {row["Category"]: row["After triage (Y)"] for row in provenance["topic_summary"]})
            by_inventory[path.name] = by_doi
        self.assertEqual(by_inventory["papers.csv"], by_inventory["supporting_information.csv"])
        self.assertEqual(provenance["unique_dois"], 13770)
        self.assertEqual(provenance["triage_counts"], {"Y": 7435, "N": 6335})
        for row in provenance["topic_summary"]:
            self.assertEqual(row["Before triage"], row["After triage (Y)"] + row["After triage (N)"])
        self.assertEqual(sum(row["Before triage"] for row in provenance["topic_summary"]), 13770)
        self.assertEqual(sum(row["After triage (N)"] for row in provenance["topic_summary"]), 6335)
        self.assertEqual(provenance["taxonomy_policy"], export.TAXONOMY_POLICY)
        self.assertFalse(provenance["generated_by_llm"])
        self.assertEqual(export.digest((folder.parent / "literature_metadata.csv").read_bytes()),
                         provenance["bibliography_sha256"])
        self.assertEqual(export.digest((ROOT / provenance["classifier_path"]).read_bytes()), provenance["classifier_sha256"])


if __name__ == "__main__":
    unittest.main()
