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
        (self.folder / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "data/manifest.json").write_text(json.dumps({"files": [{"path": "unchanged"}]}), encoding="utf-8")
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
        fields, rows = export.read_csv(self.folder / "doi_classification.csv")
        self.assertEqual(fields, ["DOI", "Classification"])
        self.assertEqual([row["DOI"] for row in rows], ["10.1234/no", "10.1234/yes"])
        _, rows = export.read_csv(self.folder / "classification_audit.csv")
        self.assertTrue(all(row["Review reason"] == "Weak evidence" for row in rows))
        yes_row = next(row for row in rows if row["Triage decision"] == "Y")
        self.assertEqual(yes_row["Primary topic category (v4)"], "Crystal engineering")
        self.assertEqual(yes_row["Framework synthesis evidence"], "Two coordination frameworks were synthesized.")
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

    def test_republication_rejects_changes_to_historical_primary_topics(self):
        export.publish(self.audit_path, self.root)
        before = {path: path.read_bytes() for path in self.folder.iterdir()}
        self.audit[0]["primary_topic_category"] = "Functional materials"
        self.write_audit()
        with self.assertRaisesRegex(ValueError, "Historical primary topic changed"):
            export.publish(self.audit_path, self.root)
        self.assertEqual(before, {path: path.read_bytes() for path in self.folder.iterdir()})


class PublishedClassificationIntegrityTests(unittest.TestCase):
    def test_public_tables_match_each_other_and_recorded_provenance(self):
        folder = ROOT / "data/metadata/literature_retrieval"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["exports"]:
            path = folder / entry["file"]
            self.assertEqual(export.digest(path.read_bytes()), entry["sha256"], path.name)
            fields, rows = export.read_csv(path)
            self.assertEqual(fields, entry["columns"], path.name)
            self.assertEqual(len(rows), entry["row_count"], path.name)
        _, compact = export.read_csv(folder / "doi_classification.csv")
        _, audit = export.read_csv(folder / "classification_audit.csv")
        by_doi = {row["DOI"]: row for row in audit}
        self.assertEqual(len(by_doi), 13770)
        self.assertEqual(len(audit), len(by_doi))
        self.assertEqual(compact, [{"DOI": row["DOI"], "Classification": row["Classification"]} for row in audit])
        self.assertTrue(all(row["Classification"] in export.CATEGORIES for row in audit))
        self.assertEqual(Counter(row["Triage decision"] for row in audit), {"Y": 7435, "N": 6335})
        yes_dois = {doi for doi, row in by_doi.items() if row["Triage decision"] == "Y"}
        for name in ("papers.csv", "supporting_information.csv"):
            fields, rows = export.read_csv(folder / name)
            self.assertEqual(fields, export.INVENTORY_FIELDS)
            self.assertEqual(len(rows), 7437)
            self.assertEqual({export.normalize_doi(row["DOI"]) for row in rows}, yes_dois)
            self.assertTrue(all(row["Classification"] == by_doi[export.normalize_doi(row["DOI"])]["Classification"] for row in rows))
        provenance = manifest["classification"]
        self.assertEqual(provenance["taxonomy_policy"], export.TAXONOMY_POLICY)
        self.assertEqual(Counter(row["Primary topic category (v4)"] for row in audit),
                         {"Chemical synthesis": 2017, "Theory & modeling": 500,
                          "Crystal engineering": 4862, "Functional materials": 6391})
        for row in audit:
            reassigned = row["Classification"] != row["Primary topic category (v4)"]
            self.assertEqual(row["Taxonomy reassigned"] == "True", reassigned)
            if reassigned:
                self.assertEqual(row["Classification"], "Chemical synthesis")
                self.assertEqual(row["Framework synthesis reported"], "True")
                self.assertTrue(row["Framework synthesis evidence"])
                self.assertTrue(row["Reassignment reason"])
        self.assertEqual(provenance["taxonomy_reassigned_count"],
                         sum(row["Taxonomy reassigned"] == "True" for row in audit))
        self.assertEqual(provenance["review_needed_count"], sum(row["Review needed"] == "True" for row in audit))
        self.assertEqual(provenance["fallback_count"], sum(row["Fallback used"] == "True" for row in audit))
        self.assertFalse(provenance["generated_by_llm"])
        self.assertEqual(export.digest((ROOT / provenance["classifier_path"]).read_bytes()), provenance["classifier_sha256"])


if __name__ == "__main__":
    unittest.main()
