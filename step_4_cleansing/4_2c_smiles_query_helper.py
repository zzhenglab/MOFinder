"""Step 4.2c SMILES query helper for MOFinder cleansing.

This script fills or standardizes a SMILES column by querying chemical names.
It is designed to sit beside the other files in ``step_4_cleansing``.

Query order:
1. PubChem PUG REST
2. CACTUS / NCI Chemical Identifier Resolver
3. OPSIN

RDKit is used to validate and canonicalize SMILES whenever it is available.
Use ``--no-rdkit`` only when you want to accept unvalidated SMILES strings.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from utils import branch_paths, configure_utf8_stdio, is_filled as repo_is_filled, print_header
except Exception:  # pragma: no cover - keeps the helper usable outside the repo.
    branch_paths = None
    repo_is_filled = None

    def configure_utf8_stdio() -> None:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    def print_header(msg: str) -> None:
        print("\n" + "=" * 80)
        print(msg)
        print("=" * 80)


TRAILING_PARENTHETICAL_RE = re.compile(r"\s+\([^()]*\)\s*$")
CACHE_COLUMNS = ["query_name", "smiles", "source", "status", "error"]
NAME_FALLBACKS = [
    "linker_1",
    "canonical_name",
    "chemical_name",
    "compound_name",
    "linker_name",
    "name",
    "Name",
    "Canonical Name",
]
SMILES_FALLBACKS = [
    "linker_1_smiles",
    "smiles",
    "SMILES",
    "canonical_smiles",
    "CanonicalSMILES",
    "rdkit_smiles",
]


@dataclass
class QueryResult:
    smiles: str | None = None
    source: str | None = None
    status: str = "not_found"
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.smiles)

    def as_row(self, query_name: str) -> dict[str, str]:
        return {
            "query_name": query_name,
            "smiles": self.smiles or "",
            "source": self.source or "",
            "status": self.status,
            "error": self.error,
        }


class SmilesQueryClient:
    """Query external name-to-SMILES services and canonicalize results."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        request_delay_seconds: float = 0.10,
        require_rdkit: bool = True,
        user_agent: str = "MOFinder-SMILES-query-helper/1.0",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.session = make_session(user_agent=user_agent)
        self.chem = load_rdkit(require=require_rdkit)
        self.query_functions: list[tuple[str, Callable[[str], str | None]]] = [
            ("pubchem", self.query_pubchem),
            ("cactus", self.query_cactus),
            ("opsin", self.query_opsin),
        ]

    def canonicalize_smiles(self, smiles: str | None) -> str | None:
        """Return RDKit canonical SMILES, or None when the string is invalid."""
        if not has_value(smiles):
            return None
        text = str(smiles).strip()
        if self.chem is None:
            return text
        mol = self.chem.MolFromSmiles(text)
        if mol is None:
            return None
        return self.chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)

    def query_pubchem(self, name: str) -> str | None:
        """Query PubChem by chemical name."""
        encoded = quote(str(name).strip(), safe="")
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{encoded}/property/CanonicalSMILES/TXT"
        )
        response = self.session.get(url, timeout=self.timeout_seconds)
        if response.status_code != 200:
            return None
        candidate = first_clean_line(response.text)
        return self.canonicalize_smiles(candidate)

    def query_cactus(self, name: str) -> str | None:
        """Query CACTUS / NCI Chemical Identifier Resolver by chemical name."""
        encoded = quote(str(name).strip(), safe="")
        url = f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/smiles"
        response = self.session.get(url, timeout=self.timeout_seconds)
        if response.status_code != 200:
            return None
        candidate = first_clean_line(response.text)
        return self.canonicalize_smiles(candidate)

    def query_opsin(self, name: str) -> str | None:
        """Query OPSIN by chemical name."""
        encoded = quote(str(name).strip(), safe="")
        url = f"https://opsin.ch.cam.ac.uk/opsin/{encoded}.json"
        response = self.session.get(url, timeout=self.timeout_seconds)
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        status = str(data.get("status", "")).upper()
        if status not in {"SUCCESS", "OK"} and not data.get("smiles"):
            return None
        return self.canonicalize_smiles(data.get("smiles"))

    def query_smiles_by_name(self, name: str) -> QueryResult:
        """Try all configured sources in order."""
        query_name = clean_name_for_query(name)
        if not has_value(query_name):
            return QueryResult(status="missing_query_name")

        last_error = ""
        for source_name, query_function in self.query_functions:
            try:
                smiles = query_function(query_name)
            except Exception as exc:  # Network and service errors should not stop a full CSV pass.
                smiles = None
                last_error = f"{source_name}: {exc.__class__.__name__}: {exc}"

            if smiles:
                return QueryResult(smiles=smiles, source=source_name, status="ok")

            if self.request_delay_seconds:
                time.sleep(self.request_delay_seconds)

        return QueryResult(status="not_found", error=last_error)


def make_session(user_agent: str) -> requests.Session:
    """Create a requests session with retry behavior for temporary API errors."""
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


def load_rdkit(*, require: bool):
    """Import RDKit lazily so help text and simple inspection still work."""
    try:
        from rdkit import Chem
    except Exception as exc:
        if require:
            raise RuntimeError(
                "RDKit is required for validated canonical SMILES. Install it, for example with "
                "`conda install -c conda-forge rdkit`, or run this helper with --no-rdkit."
            ) from exc
        return None
    return Chem


def has_value(value) -> bool:
    """Return True when a dataframe value is not empty or a string placeholder."""
    if repo_is_filled is not None:
        return bool(repo_is_filled(value))
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    text = str(value).strip()
    return text != "" and text.lower() not in {"nan", "none", "null", "na", "n/a"}


def clean_name_for_query(name: str) -> str:
    """Clean chemical names before querying external services."""
    if not has_value(name):
        return ""
    text = str(name).strip()
    return TRAILING_PARENTHETICAL_RE.sub("", text).strip()


def first_clean_line(text: str) -> str | None:
    """Extract the first useful line from a text API response."""
    if not text:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if "not found" in lower or "html" in lower or "error" in lower:
            continue
        return line
    return None


def cache_key(query_name: str) -> str:
    """Normalize a query name for cache lookup."""
    return re.sub(r"\s+", " ", str(query_name).strip()).lower()


def load_cache(path: Path | None) -> dict[str, QueryResult]:
    """Load a name-to-SMILES cache CSV."""
    if path is None or not path.exists():
        return {}
    cache_df = pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")
    cache: dict[str, QueryResult] = {}
    for _, row in cache_df.iterrows():
        query_name = str(row.get("query_name", "")).strip()
        if not query_name:
            continue
        cache[cache_key(query_name)] = QueryResult(
            smiles=str(row.get("smiles", "")).strip() or None,
            source=str(row.get("source", "")).strip() or None,
            status=str(row.get("status", "")).strip() or "not_found",
            error=str(row.get("error", "")).strip(),
        )
    return cache


def write_cache(path: Path | None, cache: dict[str, QueryResult], query_names: dict[str, str]) -> None:
    """Write the cache CSV in a stable order."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [cache[key].as_row(query_names.get(key, key)) for key in sorted(cache)]
    pd.DataFrame(rows, columns=CACHE_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")


def find_column(df: pd.DataFrame, preferred_name: str | None, fallback_names: list[str]) -> str | None:
    """Find a dataframe column by exact name, then case-insensitive alternatives."""
    if preferred_name and preferred_name in df.columns:
        return preferred_name
    lower_to_actual = {str(col).lower(): col for col in df.columns}
    candidates = [preferred_name, *fallback_names] if preferred_name else fallback_names
    for candidate in candidates:
        if not candidate:
            continue
        actual = lower_to_actual.get(str(candidate).lower())
        if actual is not None:
            return actual
    return None


def resolve_input_path(input_path: str | Path | None, branch: str | None) -> Path:
    """Resolve an explicit input path or a MOFinder branch default."""
    if input_path:
        return Path(input_path)
    if branch:
        if branch_paths is None:
            raise RuntimeError("--branch requires this file to be run inside step_4_cleansing with utils.py available.")
        paths = branch_paths(branch)
        # Step 4.2 produces s3 after linker cleanup and s4 after solvent cleanup.
        # The SMILES helper only needs the cleaned linker names, so s3 is the natural default.
        return paths["s3"]
    raise ValueError("Provide --input, or provide --branch to use the MOFinder Step 4 default paths.")


def choose_smiles_column(df: pd.DataFrame, preferred_name: str | None, name_column: str) -> str:
    """Choose or create a SMILES column."""
    if preferred_name:
        if preferred_name not in df.columns:
            df[preferred_name] = ""
        return preferred_name

    existing = find_column(df, None, SMILES_FALLBACKS)
    if existing:
        return existing

    if str(name_column).lower() == "linker_1":
        df["linker_1_smiles"] = ""
        return "linker_1_smiles"

    df["smiles"] = ""
    return "smiles"


def default_output_path(input_path: Path) -> Path:
    """Return the default output path for the filled table."""
    return input_path.with_name(f"{input_path.stem}_smiles.csv")


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as h/m/s text."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def fill_smiles_by_name(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    name_column: str | None = None,
    smiles_column: str | None = None,
    cache_csv: str | Path | None = None,
    checkpoint_csv: str | Path | None = None,
    add_metadata: bool = True,
    timeout_seconds: float = 20.0,
    request_delay_seconds: float = 0.10,
    print_every: int = 100,
    checkpoint_every: int = 500,
    print_hits: bool = False,
    print_failures: bool = False,
    limit: int | None = None,
    require_rdkit: bool = True,
    encoding: str = "utf-8",
) -> Path:
    """Fill missing or invalid SMILES values from a chemical-name column."""
    configure_utf8_stdio()
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path = Path(output_path) if output_path is not None else default_output_path(input_path)
    cache_path = Path(cache_csv) if cache_csv is not None else output_path.with_suffix(".cache.csv")
    checkpoint_path = Path(checkpoint_csv) if checkpoint_csv is not None else output_path.with_suffix(".checkpoint.csv")

    df = pd.read_csv(input_path, dtype=str, encoding=encoding).fillna("")
    selected_name_column = find_column(df, name_column, NAME_FALLBACKS)
    if selected_name_column is None:
        raise ValueError(
            "Could not find a name column. Use --name-column. "
            f"Available columns: {list(df.columns)}"
        )
    selected_smiles_column = choose_smiles_column(df, smiles_column, selected_name_column)

    metadata_columns = {
        "query_name": "smiles_query_name",
        "source": "smiles_query_source",
        "status": "smiles_query_status",
        "error": "smiles_query_error",
    }
    if add_metadata:
        for col in metadata_columns.values():
            if col not in df.columns:
                df[col] = ""

    print_header("Step 4.2c SMILES query helper")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Name column: {selected_name_column}")
    print(f"SMILES column: {selected_smiles_column}")
    print(f"Rows: {len(df):,}")
    print(f"Cache: {cache_path}")

    client = SmilesQueryClient(
        timeout_seconds=timeout_seconds,
        request_delay_seconds=request_delay_seconds,
        require_rdkit=require_rdkit,
    )
    cache = load_cache(cache_path)
    query_names = {key: key for key in cache}

    stats = Counter(
        {
            "already_canonical_existing": 0,
            "standardized_existing": 0,
            "accepted_existing_without_rdkit": 0,
            "invalid_existing": 0,
            "filled_by_cache": 0,
            "filled_by_query": 0,
            "failed_cache": 0,
            "failed_query": 0,
            "skipped_missing_name": 0,
        }
    )
    source_hits = Counter()
    initial_nonempty = int(df[selected_smiles_column].apply(has_value).sum())
    total_rows = len(df) if limit is None else min(limit, len(df))
    start_time = time.time()

    iterator = df.iterrows()
    for position, (idx, row) in enumerate(iterator, start=1):
        if limit is not None and position > limit:
            break

        raw_name = row.get(selected_name_column, "")
        raw_smiles = row.get(selected_smiles_column, "")
        query_name = clean_name_for_query(raw_name)
        needs_query = True
        row_status = ""
        row_source = ""
        row_error = ""

        if has_value(raw_smiles):
            canonical_existing = client.canonicalize_smiles(raw_smiles)
            if canonical_existing:
                original = str(raw_smiles).strip()
                df.at[idx, selected_smiles_column] = canonical_existing
                if client.chem is None:
                    stats["accepted_existing_without_rdkit"] += 1
                    row_status = "existing_unvalidated"
                elif canonical_existing == original:
                    stats["already_canonical_existing"] += 1
                    row_status = "existing_valid"
                else:
                    stats["standardized_existing"] += 1
                    row_status = "standardized_existing"
                row_source = "existing"
                needs_query = False
            else:
                df.at[idx, selected_smiles_column] = ""
                stats["invalid_existing"] += 1

        if needs_query:
            if not has_value(query_name):
                stats["skipped_missing_name"] += 1
                row_status = "missing_name"
                if print_failures:
                    print(f"[{position}/{total_rows}] skipped: missing name")
            else:
                key = cache_key(query_name)
                query_names[key] = query_name
                if key in cache:
                    result = cache[key]
                    if result.ok:
                        df.at[idx, selected_smiles_column] = result.smiles or ""
                        stats["filled_by_cache"] += 1
                        source_hits[result.source or "cache"] += 1
                        row_status = "filled_from_cache"
                        row_source = result.source or "cache"
                    else:
                        stats["failed_cache"] += 1
                        row_status = "not_found_cached"
                        row_error = result.error
                else:
                    result = client.query_smiles_by_name(query_name)
                    cache[key] = result
                    if result.ok:
                        df.at[idx, selected_smiles_column] = result.smiles or ""
                        stats["filled_by_query"] += 1
                        source_hits[result.source or "query"] += 1
                        row_status = "filled_by_query"
                        row_source = result.source or "query"
                        if print_hits:
                            print(f"[{position}/{total_rows}] filled by {row_source}: {raw_name} -> {result.smiles}")
                    else:
                        stats["failed_query"] += 1
                        row_status = result.status
                        row_error = result.error
                        if print_failures:
                            print(f"[{position}/{total_rows}] failed: {raw_name}")

        if add_metadata:
            df.at[idx, metadata_columns["query_name"]] = query_name
            df.at[idx, metadata_columns["source"]] = row_source
            df.at[idx, metadata_columns["status"]] = row_status
            df.at[idx, metadata_columns["error"]] = row_error

        if print_every and position % print_every == 0:
            elapsed = time.time() - start_time
            print(
                f"[{position}/{total_rows}] progress | "
                f"filled_query={stats['filled_by_query']} | "
                f"filled_cache={stats['filled_by_cache']} | "
                f"failed_query={stats['failed_query']} | "
                f"failed_cache={stats['failed_cache']} | "
                f"existing_ok={stats['already_canonical_existing']} | "
                f"standardized_existing={stats['standardized_existing']} | "
                f"invalid_existing={stats['invalid_existing']} | "
                f"elapsed={format_elapsed(elapsed)}"
            )

        if checkpoint_every and position % checkpoint_every == 0:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
            write_cache(cache_path, cache, query_names)
            print(f"[{position}/{total_rows}] checkpoint saved to: {checkpoint_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    if checkpoint_every:
        df.to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
    write_cache(cache_path, cache, query_names)

    final_nonempty = int(df[selected_smiles_column].apply(has_value).sum())
    elapsed = time.time() - start_time

    print_header("SMILES query summary")
    print(f"Rows processed: {total_rows:,}")
    print(f"Rows with non-empty SMILES before: {initial_nonempty:,}")
    print(f"Rows with non-empty SMILES after: {final_nonempty:,}")
    for key in sorted(stats):
        print(f"{key}: {stats[key]:,}")
    print(f"Source hit counts: {dict(source_hits)}")
    print(f"Elapsed: {format_elapsed(elapsed)}")
    print(f"Wrote: {output_path}")
    if cache_path:
        print(f"Wrote cache: {cache_path}")
    return output_path


def run(
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    branch: str | None = None,
    **kwargs,
) -> Path:
    """Programmatic entrypoint that matches the Step 4 script style."""
    resolved_input = resolve_input_path(input_path, branch)
    return fill_smiles_by_name(resolved_input, output_path, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Step 4.2c: fill and standardize SMILES from linker or chemical names."
    )
    parser.add_argument("--input", dest="input_path", default=None, help="Input CSV. Required unless --branch is used.")
    parser.add_argument("--output", dest="output_path", default=None, help="Output CSV. Default: <input>_smiles.csv")
    parser.add_argument(
        "--branch",
        choices=("positive", "negative-plans"),
        default=None,
        help="Use MOFinder Step 4 default branch input paths. Uses the _1_2_3 CSV.",
    )
    parser.add_argument("--name-column", default=None, help="Chemical-name column. Default auto-detects linker_1 first.")
    parser.add_argument("--smiles-column", default=None, help="SMILES output column. Default creates linker_1_smiles.")
    parser.add_argument("--cache", dest="cache_csv", default=None, help="Name-to-SMILES cache CSV.")
    parser.add_argument("--checkpoint", dest="checkpoint_csv", default=None, help="Checkpoint CSV.")
    parser.add_argument("--no-metadata", action="store_true", help="Do not add smiles_query_* metadata columns.")
    parser.add_argument("--timeout", dest="timeout_seconds", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--delay", dest="request_delay_seconds", type=float, default=0.10, help="Delay between API calls.")
    parser.add_argument("--print-every", type=int, default=100, help="Progress print interval. Use 0 to disable.")
    parser.add_argument("--checkpoint-every", type=int, default=500, help="Checkpoint interval. Use 0 to disable.")
    parser.add_argument("--print-hits", action="store_true", help="Print each successful query fill.")
    parser.add_argument("--print-failures", action="store_true", help="Print each failed query.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N rows for testing.")
    parser.add_argument("--no-rdkit", action="store_true", help="Accept unvalidated SMILES if RDKit is unavailable.")
    parser.add_argument("--encoding", default="utf-8", help="Input CSV encoding.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(
        input_path=args.input_path,
        output_path=args.output_path,
        branch=args.branch,
        name_column=args.name_column,
        smiles_column=args.smiles_column,
        cache_csv=args.cache_csv,
        checkpoint_csv=args.checkpoint_csv,
        add_metadata=not args.no_metadata,
        timeout_seconds=args.timeout_seconds,
        request_delay_seconds=args.request_delay_seconds,
        print_every=args.print_every,
        checkpoint_every=args.checkpoint_every,
        print_hits=args.print_hits,
        print_failures=args.print_failures,
        limit=args.limit,
        require_rdkit=not args.no_rdkit,
        encoding=args.encoding,
    )


if __name__ == "__main__":
    main()
