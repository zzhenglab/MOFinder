"""Abstract screening, input validation, and command-line workflows.

Screening records each model response and supports resuming unrecorded requests.
Saved-run evaluation and figures are provided by the evaluation and plotting
modules; they do not require an API key.
"""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import time
import uuid
import csv
import hashlib
import json
import posixpath
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import numpy as np

from mofinder.config import load_triage_config

GT_COLUMNS = ["DOI", "Consensus GT", "Annotator 1", "Annotator 1 comment",
              "Annotator 2", "Annotator 2 comment", "Annotator 3", "Annotator 3 comment",
              "Annotator 4", "Annotator 4 comment", "Vote pattern", "Resolution method", "Rule/reason"]


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_table(path, sheet=None):
    """Read CSV or XLSX cells without additional spreadsheet packages."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing input: {path}. Supply the real file; no example data are substituted.")
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            rows = list(reader)
        names = ["CSV"]
    elif path.suffix.lower() == ".xlsx":
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                shared = ["".join(t.text or "" for t in si.findall(".//s:t", NS))
                          for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
            book = ET.fromstring(z.read("xl/workbook.xml"))
            sheets = list(book.find("s:sheets", NS))
            names = [s.attrib["name"] for s in sheets]
            chosen = sheets[0] if sheet is None else next((s for s in sheets if s.attrib["name"] == sheet), None)
            if chosen is None:
                raise ValueError(f"Sheet {sheet!r} absent in {path.name}; available sheets: {names}")
            rels = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            rel_id = chosen.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rels[rel_id]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            xml = ET.fromstring(z.read(target))
            matrix = []
            for row in xml.findall("s:sheetData/s:row", NS):
                values = {}
                for cell in row.findall("s:c", NS):
                    letters = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                    index = 0
                    for letter in letters:
                        index = index * 26 + ord(letter) - 64
                    node = cell.find("s:v", NS)
                    value = "" if node is None else (node.text or "")
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)] if value else ""
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                    values[index - 1] = value
                if values and any(str(v).strip() for v in values.values()):
                    matrix.append(values)
            if not matrix:
                raise ValueError(f"No data found in {path.name}.")
            width = max(matrix[0]) + 1
            headers = [str(matrix[0].get(i, "")).strip() for i in range(width)]
            rows = [{headers[i]: r.get(i, "") for i in range(width)} for r in matrix[1:]]
    else:
        raise ValueError("Use .xlsx or .csv inputs.")
    headers = [str(x).strip() for x in headers]
    if len(headers) != len(set(headers)) or any(not x for x in headers):
        raise ValueError(f"Blank or duplicate headers in {path.name}.")
    rows = [{str(k).strip(): "" if v is None else str(v) for k, v in row.items()} for row in rows]
    return headers, rows, names


def doi_key(value):
    value = unquote(str(value)).strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi\s*:\s*", "", value).strip()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", value):
        raise ValueError(f"Invalid DOI: {value!r}")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def save_csv(rows, path, fields=None):
    path = Path(path)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    if not fields:
        fields = ["No records"]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def votes(row):
    labels = [row[f"Annotator {i}"].strip().upper() for i in range(1, 5)]
    return labels.count("Y"), labels.count("N")

def divide(a, b):
    a, b = np.broadcast_arrays(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    return np.divide(a, b, out=np.full(a.shape, np.nan), where=b != 0)


def metric_values(counts):
    c = np.asarray(counts, dtype=float)
    tp, fp, tn, fn = np.moveaxis(c, -1, 0)
    return {
        "Accuracy": divide(tp + tn, tp + fp + tn + fn), "Precision": divide(tp, tp + fp),
        "Recall": divide(tp, tp + fn), "Specificity": divide(tn, tn + fp),
        "F1": divide(2 * tp, 2 * tp + fp + fn),
        "Balanced accuracy": (divide(tp, tp + fn) + divide(tn, tn + fp)) / 2,
        "NPV": divide(tn, tn + fn),
        "MCC": divide(tp * tn - fp * fn, np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))),
    }


def confusion(y, p):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=int)
    return np.array([np.sum((y == 1) & (p == 1)), np.sum((y == 0) & (p == 1)),
                     np.sum((y == 0) & (p == 0)), np.sum((y == 1) & (p == 0))], dtype=int)


def interval(samples):
    finite = np.asarray(samples, dtype=float)
    finite = finite[np.isfinite(finite)]
    return (*np.quantile(finite, [0.025, 0.975]), len(finite)) if len(finite) else (np.nan, np.nan, 0)


def wilson(k, n):
    if n == 0:
        return np.nan, np.nan
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0., center - half), min(1., center + half)


def agreement_values(patterns, frequency):
    freq = np.asarray(frequency, dtype=float)
    if freq.ndim == 1:
        freq = freq[None, :]
    yy, nn = np.asarray(patterns, dtype=float).T
    mm = yy + nn
    all_n = freq.sum(axis=1)
    agreeing_pairs = (yy * (yy - 1) + nn * (nn - 1)) / 2
    pairs = mm * (mm - 1) / 2
    raw = divide(freq @ agreeing_pairs, freq @ pairs)
    complete = (mm == 4).astype(float)
    complete_n = freq @ complete
    po = divide(freq @ (agreeing_pairs * complete), 6 * complete_n)
    py = divide(freq @ (yy * complete), 4 * complete_n)
    pe = py ** 2 + (1 - py) ** 2
    kappa = divide(po - pe, 1 - pe)
    eligible = (mm >= 2).astype(float)
    ny, nneg = freq @ (yy * eligible), freq @ (nn * eligible)
    total = ny + nneg
    discordance = np.divide(2 * yy * nn, mm - 1, out=np.zeros_like(mm), where=mm >= 2)
    do = divide(freq @ discordance, total)
    de = divide(2 * ny * nneg, total * (total - 1))
    alpha = 1 - divide(do, de)
    unanimity = divide(freq @ (((yy == 4) | (nn == 4)).astype(float)), all_n)
    return {"Raw pairwise agreement (available ratings)": raw,
            "Fleiss kappa (four binary ratings)": kappa,
            "Krippendorff alpha (available binary ratings)": alpha,
            "Four-rater unanimity / all papers": unanimity}



def validate_inputs(metadata_file, ground_truth_file, *, sheet=None,
                    benchmark_only=True, max_papers=None):
    """Validate metadata and a single-sheet human reference without screening.

    Identical metadata duplicates are counted and collapsed within the selected
    scope. Conflicting duplicates, invalid DOIs, and non-binary consensus labels
    raise an error. Missing reference abstracts are returned explicitly.
    """
    if max_papers is not None and (not isinstance(max_papers, int) or max_papers < 1):
        raise ValueError("max_papers must be None or a positive integer.")
    headers, ground_truth, sheet_names = read_table(ground_truth_file)
    if len(sheet_names) != 1 or headers != GT_COLUMNS:
        raise ValueError("Use the supplied one-sheet workbook with the 13 specified headers in their original order.")
    ground_truth_by_doi = {}
    for row in ground_truth:
        key = doi_key(row["DOI"])
        if key in ground_truth_by_doi:
            raise ValueError(f"Duplicate reference DOI: {key}")
        if row["Consensus GT"].strip().upper() not in {"Y", "N"}:
            raise ValueError(f"Non-binary consensus for {key}; resolve it explicitly before evaluation.")
        ground_truth_by_doi[key] = row
    if not ground_truth_by_doi:
        raise ValueError("The reference contains no publications.")

    metadata_headers, metadata, _ = read_table(metadata_file, sheet)
    # DOI identifies each record; the other five fields populate the model prompt.
    aliases = {
        "DOI": ["DOI"], "title": ["Article Title", "Title"],
        "source": ["Source Title", "Source", "Journal"],
        "author_keywords": ["Author Keywords", "Keywords"],
        "keywords_plus": ["Keywords Plus"], "abstract": ["Abstract"],
    }
    header_lookup = {h.casefold(): h for h in metadata_headers}
    columns = {k: next((header_lookup[a.casefold()] for a in options if a.casefold() in header_lookup), None)
               for k, options in aliases.items()}
    if columns["DOI"] is None or columns["abstract"] is None:
        raise ValueError("Abstract metadata must contain DOI and Abstract columns.")

    papers_by_doi = {}
    identical_duplicates = 0
    for row_number, row in enumerate(metadata, 2):
        try:
            key = doi_key(row.get(columns["DOI"], ""))
        except ValueError as e:
            raise ValueError(f"Metadata row {row_number}: {e}") from e
        if benchmark_only and key not in ground_truth_by_doi:
            continue
        paper = {k: (row.get(col, "").strip() if col else "") for k, col in columns.items() if k != "DOI"}
        paper["DOI"] = key
        if key in papers_by_doi:
            if paper != papers_by_doi[key]:
                raise ValueError(f"Conflicting metadata for duplicate DOI {key}; reconcile the input explicitly.")
            identical_duplicates += 1
        papers_by_doi[key] = paper
    papers = [p for p in papers_by_doi.values() if p["abstract"]]
    if max_papers is not None:
        papers = papers[:max_papers]
    if not papers:
        raise ValueError("No nonempty abstracts are available for the selected scope. No API calls were made.")
    paper_ids = {p["DOI"] for p in papers}
    missing_reference = []
    for key, row in ground_truth_by_doi.items():
        if key not in paper_ids:
            reason = ("DOI absent from metadata" if key not in papers_by_doi else
                      "Empty abstract" if not papers_by_doi[key]["abstract"] else "Outside max_papers subset")
            missing_reference.append({"DOI": row["DOI"], "Reason": reason})

    return {
        "ground_truth": ground_truth,
        "ground_truth_by_doi": ground_truth_by_doi,
        "papers": papers,
        "paper_ids": paper_ids,
        "missing_reference": missing_reference,
        "identical_duplicates": identical_duplicates,
        "metadata_rows": len(metadata),
    }


def validation_summary(validated):
    """Return counts suitable for a local validation report."""
    return {
        "metadata_rows": validated["metadata_rows"],
        "reference_publications": len(validated["ground_truth_by_doi"]),
        "consensus_counts": dict(Counter(
            row["Consensus GT"].strip().upper() for row in validated["ground_truth"]
        )),
        "scheduled_publications": len(validated["papers"]),
        "missing_reference_publications": len(validated["missing_reference"]),
        "identical_duplicates_collapsed": validated["identical_duplicates"],
    }


def human_agreement(ground_truth, *, bootstraps=50_000, seed=42):
    """Compute the notebook's agreement estimates and publication intervals."""
    if not ground_truth:
        raise ValueError("The reference contains no publications.")
    if not isinstance(bootstraps, int) or bootstraps < 1:
        raise ValueError("bootstraps must be a positive integer.")
    pattern_counts = Counter(votes(row) for row in ground_truth)
    patterns = np.array(list(pattern_counts), dtype=int)
    frequencies = np.array(list(pattern_counts.values()), dtype=int)
    observed = agreement_values(patterns, frequencies)
    boot_frequency = np.random.default_rng(seed).multinomial(
        len(ground_truth), frequencies / frequencies.sum(), size=bootstraps
    )
    boot_agreement = agreement_values(patterns, boot_frequency)
    ratings_n = sum((y + n) * count for (y, n), count in pattern_counts.items())
    complete_n = sum(count for (y, n), count in pattern_counts.items() if y + n == 4)
    rows = []
    for name, value in observed.items():
        low, high, valid = interval(boot_agreement[name])
        rows.append({
            "Statistic": name, "Estimate": float(value[0]),
            "CI lower": float(low), "CI upper": float(high),
            "Valid bootstrap draws": valid,
            "Reference papers": len(ground_truth),
            "Complete four-binary-rating papers": complete_n,
            "Binary ratings": ratings_n,
            "Ambiguous or missing ratings": 4 * len(ground_truth) - ratings_n,
        })
    return rows



async def classify_one(client, paper, cfg, round_number, *, prompt, run_id, max_output_tokens):
    """Request a single Y/N answer and preserve failures as unscored records."""
    text = prompt.format(
        **{
            k: paper[k]
            for k in [
                "title",
                "source",
                "author_keywords",
                "keywords_plus",
                "abstract",
            ]
        }
    )

    record = {
        "Run ID": run_id,
        "DOI": paper["DOI"],
        "Title": paper["title"],
        "Configuration": cfg["name"],
        "Requested model": cfg["model"],
        "Reasoning effort": (
            cfg["reasoning_effort"]
            if cfg["reasoning_effort"] is not None
            else "none"
        ),
        "Round": round_number,
        "Agent_YN": "",
        "Status": "",
        "Raw answer": "",
        "Error": "",
        "Returned model": "",
        "Response ID": "",
        "Input tokens": 0,
        "Output tokens": 0,
        "Reasoning tokens": 0,
        "Elapsed seconds": 0,
        "Input SHA256": digest(text),
        "Completed UTC": "",
    }

    started = time.monotonic()

    try:
        request_kwargs = {
            "model": cfg["model"],
            "input": [
                {
                    "role": "user",
                    "content": text,
                }
            ],
            "max_output_tokens": max_output_tokens,
            "store": False,
        }

        # Only reasoning-capable configurations receive the reasoning argument.
        # GPT-4o receives no reasoning field at all.
        if cfg["reasoning_effort"] is not None:
            request_kwargs["reasoning"] = {
                "effort": cfg["reasoning_effort"]
            }

        response = await client.responses.create(
            **request_kwargs
        )

        raw = (response.output_text or "").strip()

        record["Raw answer"] = raw
        record["Returned model"] = getattr(response, "model", "") or ""
        record["Response ID"] = response.id

        api_status = getattr(response, "status", "")

        if api_status == "completed" and raw in {"Y", "N"}:
            record["Agent_YN"] = raw
            record["Status"] = "ok"
        else:
            record["Status"] = (
                "invalid_answer"
                if api_status == "completed"
                else str(api_status or "unknown_api_status")
            )

            record["Error"] = str(
                getattr(response, "incomplete_details", None)
                or getattr(response, "error", None)
                or "No completed single-letter Y/N answer."
            )

        usage = getattr(response, "usage", None)

        if usage:
            record["Input tokens"] = (
                getattr(usage, "input_tokens", 0) or 0
            )

            record["Output tokens"] = (
                getattr(usage, "output_tokens", 0) or 0
            )

            details = getattr(
                usage,
                "output_tokens_details",
                None,
            )

            record["Reasoning tokens"] = (
                getattr(details, "reasoning_tokens", 0) or 0
            )

    except Exception as error:
        http_status = getattr(error, "status_code", None)

        record["Status"] = (
            "configuration_error"
            if http_status in {400, 401, 403, 404, 422}
            else "api_error"
        )

        record["Error"] = re.sub(
            r"sk-[A-Za-z0-9_-]+",
            "[REDACTED]",
            str(error),
        )[:1500]

    record["Elapsed seconds"] = round(
        time.monotonic() - started,
        3,
    )

    record["Completed UTC"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return record


@dataclass
class ScreeningRun:
    """Inputs, configuration, and recorded attempts for one screening run."""

    config: dict
    prompt: str
    output_dir: Path
    papers: list
    manifest: dict
    rows: list


def _write_manifest(run):
    temporary = run.output_dir / "run_manifest.json.tmp"
    temporary.write_text(json.dumps(run.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(run.output_dir / "run_manifest.json")


def _request_key(row):
    if not isinstance(row, dict):
        raise ValueError("A saved response must be a record.")
    try:
        number = float(row["Round"])
    except (TypeError, ValueError) as error:
        raise ValueError("A saved response has an invalid round.") from error
    if isinstance(row["Round"], bool) or not number.is_integer() or number < 1:
        raise ValueError(f"Invalid saved round: {row['Round']}")
    return row["Configuration"], int(number), doi_key(row["DOI"])


def _screening_identity(config, prompt, validated):
    """Settings and input identities that must match before a run can resume."""
    return {
        "models": config["models"], "rounds": config["n_rounds"],
        "benchmark_only": config["benchmark_only"], "max_papers": config["max_papers"],
        "scheduled_publications": len(validated["papers"]),
        "reference_publications": len(validated["ground_truth_by_doi"]),
        "reference_file_sha256": hashlib.sha256(config["ground_truth_file"].read_bytes()).hexdigest(),
        "reference_labels_sha256": digest([(k, r["Consensus GT"]) for k, r in validated["ground_truth_by_doi"].items()]),
        "input_file_sha256": hashlib.sha256(config["input_file"].read_bytes()).hexdigest(),
        "scheduled_inputs_sha256": digest(validated["papers"]),
        "prompt_sha256": digest(prompt), "prompt": prompt,
        "max_output_tokens": config["max_output_tokens"],
        "statistics_seed": config["statistics_seed"], "bootstrap_replicates": config["bootstraps"],
        "max_concurrent": config["max_concurrent"], "request_timeout": config["request_timeout"],
        "save_every": config["save_every"],
    }


def prepare_screening(config_file, *, output_dir=None, resume=False):
    """Validate inputs and create a new run, or verify an existing run for resume.

    Recorded attempts, including errors and invalid answers, are retained. Resume
    dispatches only requests that have no record. A new run is needed to retry
    recorded failures or change settings.
    """
    config = load_triage_config(config_file)
    validated = validate_inputs(config["input_file"], config["ground_truth_file"],
                                sheet=config["input_sheet"], benchmark_only=config["benchmark_only"],
                                max_papers=config["max_papers"])
    prompt = config["prompt_file"].read_text(encoding="utf-8")
    # Fail on malformed placeholders before creating a run or making a request.
    prompt.format(**{k: validated["papers"][0][k] for k in
                     ["title", "source", "author_keywords", "keywords_plus", "abstract"]})
    identity = _screening_identity(config, prompt, validated)
    if resume and output_dir is None:
        raise ValueError("Resume requires an explicit output_dir.")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    folder = (Path(output_dir).expanduser().resolve() if output_dir is not None
              else config["output_root"] / run_id)
    rows = []
    if resume:
        manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
        changed = [key for key, value in identity.items() if manifest.get(key) != value]
        if changed:
            raise ValueError("Cannot resume with changed or missing run settings: " + ", ".join(changed))
        source = folder / "responses.jsonl"
        if source.exists():
            for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as error:
                        raise ValueError(f"Invalid response record on line {number}; recover the file before resuming.") from error
        elif (folder / "predictions.csv").exists():
            raise ValueError("Resume requires responses.jsonl when predictions.csv exists.")
        expected = {(cfg["name"], r, paper["DOI"])
                    for cfg in config["models"] for r in range(1, config["n_rounds"] + 1)
                    for paper in validated["papers"]}
        seen = set()
        configs = {cfg["name"]: cfg for cfg in config["models"]}
        papers = {paper["DOI"]: paper for paper in validated["papers"]}
        for row in rows:
            key = _request_key(row)
            if key not in expected or key in seen or row.get("Run ID") != manifest["run_id"]:
                raise ValueError("Saved responses contain a duplicate or mismatched request.")
            cfg, paper = configs[key[0]], papers[key[2]]
            text = prompt.format(**{k: paper[k] for k in
                                  ["title", "source", "author_keywords", "keywords_plus", "abstract"]})
            if (row.get("Requested model") != cfg["model"]
                    or row.get("Reasoning effort") != (cfg["reasoning_effort"] or "none")
                    or row.get("Input SHA256") != digest(text)):
                raise ValueError("Saved response configuration or input does not match the run.")
            if not row.get("Status") or (row["Status"] == "ok" and row.get("Agent_YN") not in {"Y", "N"}):
                raise ValueError("Saved response has an invalid status or label.")
            seen.add(key)
    else:
        folder.mkdir(parents=True, exist_ok=False)
        manifest = {
            "run_id": run_id, "created_utc": datetime.now(timezone.utc).isoformat(),
            "prediction_source": "New Responses API calls from mofinder.literature.triage",
            "completed": False, **identity,
        }
        save_csv(validated["missing_reference"], folder / "reference_not_screened.csv", ["DOI", "Reason"])
        save_csv(validated["ground_truth"], folder / "reference_used.csv", GT_COLUMNS)
    run = ScreeningRun(config, prompt, folder, validated["papers"], manifest, rows)
    if not resume:
        _write_manifest(run)
    return run


async def screen_all(client, run):
    """Screen unrecorded requests with bounded concurrency and durable responses."""
    config, rows = run.config, run.rows
    expected = len(run.papers) * len(config["models"]) * config["n_rounds"]
    completed_keys = {_request_key(row) for row in rows}
    stopped = {row["Configuration"] for row in rows if row["Status"] == "configuration_error"}
    semaphore = asyncio.Semaphore(config["max_concurrent"])

    async def classify(paper, cfg, round_number):
        return await classify_one(client, paper, cfg, round_number, prompt=run.prompt,
                                  run_id=run.manifest["run_id"], max_output_tokens=config["max_output_tokens"])

    async def worker(paper, cfg, round_number):
        async with semaphore:
            return await classify(paper, cfg, round_number)

    def record_answer(record):
        rows.append(record)
        with (run.output_dir / "responses.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
        if len(rows) == 1 or len(rows) % config["save_every"] == 0:
            save_csv(rows, run.output_dir / "predictions.csv")
            print(f"Saved {len(rows)}/{expected}: {record['Configuration']}, round {record['Round']}, "
                  f"{record['DOI']} → {record['Agent_YN'] or record['Status']}")

    tasks = []
    run.manifest["completed"] = False
    _write_manifest(run)
    try:
        for cfg in config["models"]:
            if cfg["name"] in stopped:
                continue
            pending = [(paper, r) for r in range(1, config["n_rounds"] + 1) for paper in run.papers
                       if (cfg["name"], r, paper["DOI"]) not in completed_keys]
            if not pending:
                continue
            # Test the first pending request before scheduling this configuration.
            paper, round_number = pending[0]
            first = await classify(paper, cfg, round_number)
            record_answer(first)
            if first["Status"] == "configuration_error":
                print(f"Stopped {cfg['name']}: {first['Error']}")
                stopped.add(cfg["name"])
                continue
            tasks = [asyncio.create_task(worker(paper, cfg, r)) for paper, r in pending[1:]]
            for finished in asyncio.as_completed(tasks):
                record_answer(await finished)
            tasks = []
        run.manifest["completed"] = True
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        save_csv(rows, run.output_dir / "predictions.csv")
        run.manifest["recorded_requests"] = len(rows)
        run.manifest["valid_answers"] = sum(row["Status"] == "ok" for row in rows)
        run.manifest["expected_requests"] = expected
        run.manifest["stopped_configurations"] = sorted(stopped)
        _write_manifest(run)
    return run


async def screen(config_file, *, output_dir=None, resume=False, api_key=None, client=None):
    """Run screening with an explicit client or OPENAI_API_KEY.

    This asynchronous function can be awaited directly from a notebook. The
    command-line entry point supplies its own event loop.
    """
    config = load_triage_config(config_file)
    validated = validate_inputs(config["input_file"], config["ground_truth_file"],
                                sheet=config["input_sheet"], benchmark_only=config["benchmark_only"],
                                max_papers=config["max_papers"])
    if client is None:
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Set OPENAI_API_KEY before starting model screening.")
        from openai import AsyncOpenAI
    run = prepare_screening(config_file, output_dir=output_dir, resume=resume)
    print(json.dumps(validation_summary(validated), indent=2))
    print("Output folder:", run.output_dir)
    if client is not None:
        return await screen_all(client, run)
    async with AsyncOpenAI(api_key=api_key, timeout=config["request_timeout"], max_retries=2) as api_client:
        return await screen_all(api_client, run)


def main(argv=None):
    """Run screening or offline validation, statistics, and saved-run analysis."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["validate-inputs", "human-agreement"]:
        command = commands.add_parser(name)
        command.add_argument("--metadata", type=Path, required=True)
        command.add_argument("--ground-truth", type=Path, required=True)
        command.add_argument("--sheet", default=None)
        command.add_argument("--all-metadata", action="store_true")
        command.add_argument("--bootstraps", type=int, default=50_000)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--output-dir", type=Path)
    command = commands.add_parser("screen", help="Create or resume a model screening run.")
    command.add_argument("--config", type=Path, default=Path("configs/abstract_triage.json"))
    command.add_argument("--output-dir", type=Path)
    command.add_argument("--resume", action="store_true")
    command = commands.add_parser("analyze", help="Analyze saved predictions without API calls.")
    command.add_argument("--run-dir", type=Path, required=True)
    command.add_argument("--ground-truth", type=Path, required=True)
    command.add_argument("--output-dir", type=Path)
    command.add_argument("--bootstraps", type=int, default=50_000)
    command.add_argument("--seed", type=int, default=42)
    command.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "screen":
            if args.resume and args.output_dir is None:
                raise ValueError("--resume requires --output-dir.")
            run = asyncio.run(screen(args.config, output_dir=args.output_dir, resume=args.resume))
            print(f"Recorded {len(run.rows)} attempts; {run.manifest['valid_answers']} valid answers.")
            return 0 if run.manifest["valid_answers"] == run.manifest["expected_requests"] else 1
        if args.command == "analyze":
            from mofinder.evaluation.triage import load_saved_run, evaluate_run
            context = evaluate_run(load_saved_run(args.run_dir, args.ground_truth,
                                   output_dir=args.output_dir, bootstraps=args.bootstraps,
                                   statistics_seed=args.seed))
            if not args.no_plots:
                from mofinder.plotting.triage import plot_results
                plot_results(context)
            print("Analysis folder:", context["output_dir"])
            return 0
        validated = validate_inputs(args.metadata, args.ground_truth,
                                    sheet=args.sheet, benchmark_only=not args.all_metadata)
        summary = validation_summary(validated)
        agreement_rows = (human_agreement(validated["ground_truth"], bootstraps=args.bootstraps, seed=args.seed)
                          if args.command == "human-agreement" else None)
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            (args.output_dir / "validation_summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            save_csv(validated["missing_reference"], args.output_dir / "reference_not_screened.csv", ["DOI", "Reason"])
            if agreement_rows is not None:
                save_csv(agreement_rows, args.output_dir / "human_agreement.csv")
        print(json.dumps(summary, indent=2))
        if agreement_rows is not None:
            print(json.dumps(agreement_rows, indent=2))
        if validated["missing_reference"]:
            print("Reference publications missing from the selected abstracts:")
            print(json.dumps(validated["missing_reference"], indent=2))
            return 1
        return 0
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
        parser.exit(2, f"Triage failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
