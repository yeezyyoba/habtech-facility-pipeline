import argparse
import os
import re
import linktransformer as lt
import pandas as pd

MFR_PATH = "mfr_facilities_202607291153.csv"
DHIS2_XLSX_PATH = "dhis2_echis_mfr_facilities.xlsx"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Confidence Score Cutoffs
SCORE_HIGH = 0.90
SCORE_MEDIUM = 0.80
SCORE_LOW = 0.70


def normalize_geo(val):
    """Standardizes regional administrative names to guarantee exact blocking alignment."""
    if pd.isna(val):
        return "unknown"
    val = str(val).lower().strip()

    # Strip administrative noise words
    pattern = r"\b(regional health bureau|region|city administration|administration|zone health department|zonal health department|health department|department|zone|zonal|town|rural|city|zhd|hd|office|dept)\b"
    val = re.sub(pattern, "", val)
    val = re.sub(r"[\s\-]+", "", val)

    # Harmonize spelling differences between MFR and DHIS2
    fixes = {
        "gojam": "gojjam",  # Aligns MFR 'West Gojam' with DHIS2 'West Gojjam'
        "gonder": "gondar",
        "shewa": "shoa",
        "gumuz": "gumz",
        "oromiya": "oromia",
        "oromya": "oromia",
        "wolaita": "welayta",
        "wolayta": "welayta",
        "swe": "southwestethiopia",
        "semien": "north",
        "debub": "south",
        "misraq": "east",
        "mirab": "west",
    }

    for k, v in fixes.items():
        val = val.replace(k, v)

    return val.strip() or "unknown"


def clean_facility_name(val):
    """Strips generic facility types so LinkTransformer compares actual facility proper names."""
    if pd.isna(val):
        return ""
    val = str(val).lower().strip()
    suffixes = [
        "health center",
        "health post",
        "primary hospital",
        "general hospital",
        "referral hospital",
        "phcu",
        "worho",
        "drug store",
        "pharmacy",
        "clinic",
        "hc",
        "hp",
        "hospital",
    ]
    for s in suffixes:
        val = re.sub(rf"\b{s}\b", "", val)
    return re.sub(r"\s+", " ", val).strip()


def find_column(df, candidates, default):
    """Helper to locate potential column name variations."""
    for col in candidates:
        if col in df.columns:
            return col
    return default


def load_data():
    """Loads and pre-processes both MFR and DHIS2 dataframes."""
    mfr = pd.read_csv(MFR_PATH, low_memory=False)
    dhis2 = pd.read_excel(DHIS2_XLSX_PATH, sheet_name="dhis2")

    # Identify region and zone columns
    mfr_region_col = find_column(
        mfr, ["region", "regional", "Region"], "region"
    )
    dhis2_region_col = find_column(
        dhis2, ["region", "regional", "Region"], "regional"
    )

    mfr["display_region"] = (
        mfr[mfr_region_col] if mfr_region_col in mfr.columns else "Unknown"
    )
    dhis2["display_region"] = (
        dhis2[dhis2_region_col]
        if dhis2_region_col in dhis2.columns
        else "Unknown"
    )

    # Normalize region for candidate blocking
    mfr["region_norm"] = mfr["display_region"].apply(normalize_geo)
    dhis2["region_norm"] = dhis2["display_region"].apply(normalize_geo)

    # Pre-clean facility names for LinkTransformer
    mfr["clean_name"] = mfr["name"].apply(clean_facility_name)
    dhis2["clean_name"] = dhis2["name"].apply(clean_facility_name)

    return mfr, dhis2


def score_to_confidence(score):
    """Categorizes numerical similarity scores into qualitative confidence levels."""
    if score is None or pd.isna(score):
        return "none"
    if score >= SCORE_HIGH:
        return "high"
    if score >= SCORE_MEDIUM:
        return "medium"
    if score >= SCORE_LOW:
        return "low"
    return "none"


def run_link(mfr_subset, dhis2):
    """Executes LinkTransformer blocking on region_norm."""
    mfr_subset = mfr_subset.copy()
    dhis2 = dhis2.copy()

    mfr_subset["region_norm"] = mfr_subset["region_norm"].fillna("unknown")
    dhis2["region_norm"] = dhis2["region_norm"].fillna("unknown")

    matched = lt.merge_blocking(
        df1=mfr_subset,
        df2=dhis2,
        merge_type="1:1",
        on="clean_name",
        blocking_vars=["region_norm"],
        model=MODEL,
        suffixes=("_mfr", "_dhis2"),
    )
    return matched


def build_output_records(mfr_subset, matched_df):
    """Constructs output records preserving original mfr_id and mfr_name across all rows."""
    results = []
    matched_mfr_ids = set()

    if not matched_df.empty:
        for _, row in matched_df.iterrows():
            mfr_id = row.get("id_mfr") if "id_mfr" in row else row.get("id")
            mfr_name = (
                row.get("name_mfr") if "name_mfr" in row else row.get("name")
            )

            score = row.get("score")
            confidence = score_to_confidence(score)
            score_str = (
                f"{score:.3f}"
                if (score is not None and not pd.isna(score))
                else "N/A"
            )

            dhis2_uid = (
                (
                    row.get("uid_dhis2")
                    if "uid_dhis2" in row
                    else row.get("uid")
                )
                if confidence != "none"
                else None
            )

            if pd.notna(mfr_id):
                matched_mfr_ids.add(mfr_id)

            reason = (
                f"LinkTransformer score {score_str} within region blocked"
                " candidates"
                if confidence != "none"
                else f"LinkTransformer score below cutoff ({score_str})"
            )

            results.append({
                "mfr_id": mfr_id,
                "mfr_name": mfr_name,
                "dhis2_uid": dhis2_uid,
                "confidence": confidence,
                "reason": reason,
            })

    # Catch unmatched records so no MFR rows/IDs are dropped
    for _, row in mfr_subset.iterrows():
        mfr_id = row.get("id")
        if mfr_id not in matched_mfr_ids:
            results.append({
                "mfr_id": mfr_id,
                "mfr_name": row.get("name"),
                "dhis2_uid": None,
                "confidence": "none",
                "reason": (
                    "LinkTransformer similarity score N/A within region blocked"
                    " candidates"
                ),
            })

    return results


def run_demo(out_path="output.csv"):
    """Runs linkage test on selected demo facilities."""
    print("Loading project datasets...")
    mfr, dhis2 = load_data()

    demo_names = [
        "Gendawuha Health Center",
        "Wegedad Health Center",
        "Tesfaye Drug store",
    ]
    subset = mfr[
        mfr["name"].isin(demo_names) & (mfr["region_norm"] == "amhara")
    ].copy()

    print("\n--- Running Demo Linkage ---")
    matched = run_link(subset, dhis2)
    results = build_output_records(subset, matched)

    out_df = pd.DataFrame(results)
    out_df.to_csv(out_path, mode="w", index=False)
    print(f"\nSaved {out_path} successfully:")
    print(out_df.to_string())


def run_batch(limit, out_path="output.csv"):
    """Runs batch linkage across all unlinked MFR facilities."""
    print("Loading project datasets...")
    mfr, dhis2 = load_data()

    mfr_dhis2_col = find_column(mfr, ["dhis2_id", "dhis2_uid"], "dhis2_id")
    if mfr_dhis2_col in mfr.columns:
        mfr[mfr_dhis2_col] = mfr[mfr_dhis2_col].replace(
            r"^\s*$", pd.NA, regex=True
        )
        unlinked = mfr[mfr[mfr_dhis2_col].isna()].head(limit).copy()
    else:
        unlinked = mfr.head(limit).copy()

    print(
        f"Processing {len(unlinked)} unlinked facilities via"
        " LinkTransformer..."
    )

    if unlinked.empty:
        print("No unlinked facilities remaining to process.")
        return

    matched = run_link(unlinked, dhis2)
    results = build_output_records(unlinked, matched)

    out_df = pd.DataFrame(results)

    # Clean out any blank invalid rows
    out_df = out_df[out_df["mfr_id"].notnull() | out_df["mfr_name"].notnull()]

    # Overwrite freshly (mode='w') to prevent corrupted appends
    out_df.to_csv(out_path, mode="w", index=False)
    print(
        f"\nBatch complete: {len(out_df)} valid facilities written to ->"
        f" {out_path}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "batch"], default="batch")
    ap.add_argument("--limit", type=int, default=35000)
    ap.add_argument("--out", default="output.csv")
    args = ap.parse_args()

    if args.mode == "demo":
        run_demo(out_path=args.out)
    else:
        run_batch(limit=args.limit, out_path=args.out)