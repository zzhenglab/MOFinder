"""Match article and supporting-information files to an literature retrieval inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import warnings


MANIFEST_COLUMNS = ["DOI", "Main File", "SI File"]
COUNT_COLUMNS = [
    "Main Words", "SI Words", "Combined Words",
    "Main Tokens", "SI Tokens", "Combined Tokens",
]
_WORD_RE = re.compile(r"\b\w+\b", flags=re.UNICODE)


def load_config(config_file):
    """Resolve paths relative to project_root and the configuration file."""
    config_file = Path(config_file).expanduser().resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    root = (config_file.parent / config.get("project_root", "..")).resolve()
    defaults = {
        "input_file": "data/metadata/literature_retrieval/supporting_information.csv",
        "article_dir": "data/local/articles",
        "si_dir": "data/local/supporting_information",
        "manifest_file": "results/extraction/document_manifest.csv",
        "matched_inventory_file": "results/extraction/matched_inventory.csv",
        "summary_file": "results/extraction/document_matching_summary.json",
        "counts_file": "results/extraction/document_counts.csv",
        "counts_summary_file": "results/extraction/document_counts_summary.json",
        "plots_dir": "results/extraction/document_count_plots",
    }
    for key, default in defaults.items():
        config[key] = (root / Path(config.get(key, default)).expanduser()).resolve()
    config["project_root"] = root
    config.setdefault("tokenizer_model", "gpt-4o")
    config.setdefault("tokenizer_fallback", "cl100k_base")
    return config


def read_table(path):
    """Read CSV or XLSX while retaining DOI, status and path strings."""
    import pandas as pd

    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, dtype=str, keep_default_na=False)
    raise ValueError(f"Expected a CSV or XLSX inventory: {path}")


def _write_table(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        frame.to_csv(path, index=False)
    elif path.suffix.lower() == ".xlsx":
        frame.to_excel(path, index=False)
    else:
        raise ValueError(f"Expected a CSV or XLSX output: {path}")


def is_empty(value):
    import pandas as pd

    return pd.isna(value) or str(value).strip().lower() in {"", "nan", "none"}


def doi_to_base(doi_raw):
    """Remove DOI URL prefixes and replace slashes with underscores."""
    doi = str(doi_raw).strip()
    doi = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip().replace("/", "_")


def _file_lookup(directory, extensions):
    lookup = {}
    if directory.is_dir():
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in extensions:
                key = path.name.lower()
                if key in lookup:
                    raise ValueError(
                        f"Ambiguous filenames differ only in case: {lookup[key]} and {path.name}"
                    )
                lookup[key] = path.name
    return lookup


def match_documents(frame, article_dir, si_dir):
    """Reconcile every inventory row against the files currently present.

    Rows, duplicate DOIs and additional metadata retain their original order.
    Returned download flags describe file presence, independent of old flags.
    """
    import pandas as pd

    article_dir, si_dir = Path(article_dir).resolve(), Path(si_dir).resolve()
    if not si_dir.is_dir():
        raise FileNotFoundError(f"SI folder not found: {si_dir}")
    if not article_dir.is_dir():
        warnings.warn(f"Main article folder not found; matching skipped: {article_dir}", stacklevel=2)

    updated = frame.copy(deep=True)
    updated.columns = [str(column).strip() for column in updated.columns]
    if "DOI" not in updated.columns:
        raise KeyError('Column "DOI" not found in the inventory.')
    if updated.columns.duplicated().any():
        raise ValueError("Inventory column names must be unique after trimming whitespace.")
    # Collect available filenames using a case-insensitive lookup.
    si_lookup = _file_lookup(si_dir, {".pdf", ".docx", ".doc"})
    main_lookup = _file_lookup(article_dir, {".pdf"})
    found_si_col, found_main_col = "Found SI Filename", "Matched Main Filename"
    output_columns = ["SI Downloaded", "Downloaded", found_si_col, found_main_col, "SI File", "Main File"]
    for column in output_columns:
        # Download flags retain the inventory convention of integer 1 or blank.
        updated[column] = pd.Series("", index=updated.index, dtype=object)

    for idx in updated.index:
        doi = updated.at[idx, "DOI"]
        if is_empty(doi):
            continue
        base = doi_to_base(doi)
        # SI candidates retain the original PDF, DOCX, DOC preference.
        for extension in (".pdf", ".docx", ".doc"):
            candidate = f"{base}_SI{extension}".lower()
            if candidate in si_lookup:
                name = si_lookup[candidate]
                updated.at[idx, "SI Downloaded"] = 1
                updated.at[idx, found_si_col] = name
                updated.at[idx, "SI File"] = str(si_dir / name)
                break
        candidate = f"{base}.pdf".lower()
        if candidate in main_lookup:
            name = main_lookup[candidate]
            updated.at[idx, "Downloaded"] = 1
            updated.at[idx, found_main_col] = name
            updated.at[idx, "Main File"] = str(article_dir / name)

    si_present = updated["SI Downloaded"].eq(1)
    main_present = updated["Downloaded"].eq(1)
    doi_bases = {doi_to_base(value).lower() for value in updated["DOI"] if not is_empty(value)}

    def unmatched(lookup, *, si=False):
        result = []
        for name_lower, name_original in lookup.items():
            base = Path(name_lower).stem
            if si and base.endswith("_si"):
                base = base[:-3]
            if base not in doi_bases:
                result.append(name_original)
        return sorted(result)

    summary = {
        "rows": len(updated),
        "main_present": int(main_present.sum()),
        "si_present": int(si_present.sum()),
        "both_present": int((main_present & si_present).sum()),
        "only_main": int((main_present & ~si_present).sum()),
        "only_si": int((~main_present & si_present).sum()),
        "neither": int((~main_present & ~si_present).sum()),
        "missing_doi_rows": int(updated["DOI"].map(is_empty).sum()),
        "article_dir_exists": article_dir.is_dir(),
        "unmatched_main_files": unmatched(main_lookup),
        "unmatched_si_files": unmatched(si_lookup, si=True),
    }
    return updated, updated.loc[:, MANIFEST_COLUMNS].copy(), summary


def _check_distinct_paths(source, *outputs):
    paths = [Path(path).resolve() for path in (source, *outputs)]
    if len(paths) != len(set(paths)):
        raise ValueError("Input and output paths must be distinct; literature retrieval inventories are read-only.")


def _write_json(value, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_matching(config):
    """Save a separate matched inventory, extraction manifest and summary."""
    _check_distinct_paths(config["input_file"], config["manifest_file"],
                          config["matched_inventory_file"], config["summary_file"])
    updated, manifest, summary = match_documents(
        read_table(config["input_file"]), config["article_dir"], config["si_dir"]
    )
    _write_table(updated, config["matched_inventory_file"])
    _write_table(manifest, config["manifest_file"])
    _write_json(summary, config["summary_file"])
    return summary


def read_pdf_text(path):
    """Extract PDF text with the original backend preference and empty fallback."""
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            raise ImportError("PDF counting requires pdfminer.six or PyPDF2.") from exc
        try:
            with Path(path).open("rb") as stream:
                text_parts = []
                for page in PdfReader(stream).pages:
                    try:
                        text_parts.append(page.extract_text() or "")
                    except Exception:
                        text_parts.append("")
                return "\n".join(text_parts)
        except Exception:
            return ""
    try:
        return extract_text(str(path)) or ""
    except Exception:
        return ""


def count_words(text):
    return len(_WORD_RE.findall(text)) if text else 0


def _safe_path(value):
    if is_empty(value):
        return None
    path = Path(str(value).strip()).expanduser()
    return path if path.is_file() else None


def count_documents(frame, *, encoding=None, tokenizer_model="gpt-4o", tokenizer_fallback="cl100k_base"):
    """Fill missing counts; Combined prefers SI, including an SI count of zero.

    PDF extraction failures and non-PDF files receive zero counts, preserving
    the original notebook convention. Missing files retain missing counts.
    Existing values are retained, and diagnostics distinguish these cases.
    """
    import numpy as np
    import pandas as pd

    if encoding is None:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(tokenizer_model)
        except Exception:
            encoding = tiktoken.get_encoding(tokenizer_fallback)
    counted = frame.copy(deep=True)
    for column in ("Main File", "SI File"):
        if column not in counted:
            counted[column] = ""
    for column in COUNT_COLUMNS:
        if column not in counted:
            counted[column] = np.nan
        counted[column] = counted[column].map(lambda value: np.nan if is_empty(value) else value)

    diagnostics = {"processed_files": 0, "empty_text_files": [], "unsupported_files": [], "missing_files": []}
    for idx in counted.index:
        for prefix in ("Main", "SI"):
            value = counted.at[idx, f"{prefix} File"]
            path = _safe_path(value)
            words_column, tokens_column = f"{prefix} Words", f"{prefix} Tokens"
            if path is None:
                if not is_empty(value):
                    diagnostics["missing_files"].append(str(value))
                continue
            if not (is_empty(counted.at[idx, words_column]) or is_empty(counted.at[idx, tokens_column])):
                continue
            if path.suffix.lower() != ".pdf":
                diagnostics["unsupported_files"].append(str(path))
                text = ""
            else:
                text = read_pdf_text(path)
                if not text:
                    diagnostics["empty_text_files"].append(str(path))
            if is_empty(counted.at[idx, words_column]):
                counted.at[idx, words_column] = count_words(text)
            if is_empty(counted.at[idx, tokens_column]):
                counted.at[idx, tokens_column] = len(encoding.encode(text)) if text else 0
            diagnostics["processed_files"] += 1

    # Combined columns use SI when present, otherwise the main article.
    for metric in ("Words", "Tokens"):
        counted[f"Combined {metric}"] = counted[f"SI {metric}"].combine_first(counted[f"Main {metric}"])
    diagnostics["statistics"] = {}
    for column in COUNT_COLUMNS:
        series = pd.to_numeric(counted[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        diagnostics["statistics"][column] = {
            "n": len(series), "average": float(series.mean()) if len(series) else 0.0,
            "total": int(series.sum()) if len(series) else 0,
        }
    return counted, diagnostics


def plot_counts(frame, output_dir):
    """Save the six 50-bin word/token histograms from the counting notebook."""
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for column in COUNT_COLUMNS:
        series = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        figure, axes = plt.subplots()
        axes.hist(series, bins=50)
        label, metric = column.rsplit(" ", 1)
        axes.set(title=f"{label} {metric.lower()} distribution", xlabel=metric, ylabel="Count")
        path = output_dir / (column.lower().replace(" ", "_") + ".png")
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)
    return paths


def run_counting(config, *, plots=False):
    """Count a matched inventory, reusing a counts file only for the same rows."""
    _check_distinct_paths(config["input_file"], config["matched_inventory_file"],
                          config["manifest_file"], config["counts_file"], config["counts_summary_file"])
    matched = read_table(config["matched_inventory_file"])
    if Path(config["counts_file"]).is_file():
        previous = read_table(config["counts_file"])
        if not previous.loc[:, MANIFEST_COLUMNS].equals(matched.loc[:, MANIFEST_COLUMNS]):
            raise ValueError("Existing count rows differ from the matched inventory. Select a new counts_file.")
        for column in COUNT_COLUMNS:
            if column in previous:
                matched[column] = previous[column]
    counted, summary = count_documents(matched, tokenizer_model=config["tokenizer_model"],
                                       tokenizer_fallback=config["tokenizer_fallback"])
    _write_table(counted, config["counts_file"])
    _write_json(summary, config["counts_summary_file"])
    if plots:
        plot_counts(counted, config["plots_dir"])
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("match", "count"))
    parser.add_argument("--config", default="configs/document_matching.json")
    parser.add_argument("--input-file", help="Override the literature retrieval inventory for matching.")
    parser.add_argument("--article-dir", help="Override the article folder.")
    parser.add_argument("--si-dir", help="Override the supporting-information folder.")
    parser.add_argument("--plots", action="store_true", help="Save count histograms with the count action.")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    for key in ("input_file", "article_dir", "si_dir"):
        if getattr(args, key):
            config[key] = Path(getattr(args, key)).expanduser().resolve()
    summary = run_matching(config) if args.action == "match" else run_counting(config, plots=args.plots)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
