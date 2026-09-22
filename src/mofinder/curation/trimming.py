# Step 7: trim only article_trial_or_failure == "no"; preserve "yes" rows.
import re
from pathlib import Path
import pandas as pd





AUTOCLAVE_PAT = re.compile(r"autoclave|vessel|container|reactor", re.I)
VIAL_FLASK_PAT = re.compile(
    r"\bvial\b|\bflask\b|\btube\b|\bdish\b|\bglass\b|\bbottle\b|\bjar\b|\bbeaker\b", re.I
)
REFLUX_PAT = re.compile(r"reflux", re.I)


def has_vessel_signal(text):
    if text is None or pd.isna(text):
        return False
    t = str(text)
    return bool(AUTOCLAVE_PAT.search(t) or VIAL_FLASK_PAT.search(t) or REFLUX_PAT.search(t))


def stage7_parse_yield(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if re.fullmatch(r"[-+]?\d*\.?\d+%?", s):
        try:
            return float(s.rstrip("%"))
        except ValueError:
            return None
    return None


def apply_p_trimming(raw, top_n=10, yield_bottom_frac=0.10, verbose=True):
    """Apply DOI-level cuts only to papers marked article_trial_or_failure=no.

    Rows marked yes remain unchanged. No is_success column is needed.
    A paper with mixed flags is protected in full. Output fields and row order match the input.
    """
    if not isinstance(top_n, int) or top_n < 0:
        raise ValueError("top_n must be a nonnegative integer.")
    if not 0 < yield_bottom_frac < 1:
        raise ValueError("yield_bottom_frac must be between 0 and 1.")
    required = {"doi", "article_trial_or_failure", "vessel_type", "yield_percent"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing CSV columns: {sorted(missing)}")
    if not raw.index.is_unique:
        raise ValueError("The input dataframe must have a unique row index.")

    flags = raw["article_trial_or_failure"].fillna("").astype(str).str.strip().str.lower()
    invalid = ~flags.isin(["yes", "no"])
    if invalid.any():
        raise ValueError(f"Unexpected article_trial_or_failure values: {flags[invalid].unique().tolist()}")
    doi_norm = (
        raw["doi"].fillna("").astype(str).str.strip().str.lower()
        .str.replace(r"^https?://(?:dx\.)?doi\.org/", "", regex=True)
        .str.replace(r"^doi:\s*", "", regex=True)
        .str.replace(r"^(10\.\d{4,9})_", r"\1/", regex=True)
        .str.strip()
    )
    if not doi_norm.str.fullmatch(r"10\.\d{4,9}/\S+").all():
        raise ValueError("Some rows lack a usable DOI. Resolve those before grouping papers.")

    # Select the target papers once, before applying the three cuts.
    eligible = flags.eq("no").groupby(doi_norm).transform("all")
    target = raw.loc[eligible].copy()
    protected = raw.loc[~eligible].copy()

    def report(label, frame):
        if verbose:
            print(f"{label}: {len(frame):,} rows / {doi_norm.loc[frame.index].nunique():,} papers")

    report("Target (article_trial_or_failure=no)", target)

    # Cut 1: keep strictly more than 50% recognized vessel signals.
    # Exactly 50% is excluded.
    # An empty target must still have a numeric-compatible dtype for groupby.
    signal = target["vessel_type"].map(has_vessel_signal).astype(bool)
    signal_frac = signal.groupby(doi_norm.loc[target.index]).transform("mean")
    target = target.loc[signal_frac > 0.5].copy()
    report("After vessel-signal majority cut", target)

    # Cut 2: drop the top N remaining target papers by row count.
    row_counts = target.groupby(doi_norm.loc[target.index]).size().sort_values(ascending=False)
    top_dois = row_counts.head(top_n).index
    target = target.loc[~doi_norm.loc[target.index].isin(top_dois)].copy()
    report(f"After top-{top_n} cut", target)

    # Cut 3: numeric yields only. Keep missing/unparseable yields unchanged.
    # Inclusive cutoff removes all ties, which can exceed the stated fraction.
    yields = target["yield_percent"].map(stage7_parse_yield)
    numeric = yields.notna()
    cutoff = None
    if numeric.any():
        cutoff = yields.loc[numeric].quantile(yield_bottom_frac)
        drop = numeric & yields.le(cutoff)
        target = target.loc[~drop].copy()
    report(f"After bottom-{yield_bottom_frac:.0%} yield cut (cutoff={cutoff})", target)

    # Select original rows in their original order, without adding helpers.
    keep = raw.index.isin(target.index) | raw.index.isin(protected.index)
    result = raw.loc[keep].copy()
    pd.testing.assert_frame_equal(result.loc[protected.index], protected)
    if verbose:
        print(f"Protected yes rows: {int(flags.eq('yes').sum()):,} (all unchanged)")
        mixed_no = int((flags.eq("no") & ~eligible).sum())
        if mixed_no:
            print(f"Also protected: {mixed_no:,} no rows from papers with mixed flags")
        print(f"TOTAL CSV: {len(raw):,} -> {len(result):,} ({len(raw)-len(result):,} dropped)")
    return result






























def clean(input_path, output_path, *, top_n=10, yield_bottom_frac=0.10):
    """Trim positive-only papers and save all retained rows in input order."""
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Trimming requires distinct input and output files.")
    original = pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    trimmed = apply_p_trimming(original, top_n=top_n, yield_bottom_frac=yield_bottom_frac)
    trimmed.to_csv(output_path, index=False, encoding="utf-8-sig")
    return trimmed
