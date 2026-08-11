"""
LLM-based facility linking: MFR (Master Facility Registry) <-> DHIS2 hierarchy

Three-stage pipeline:
  1. Region normalization (strip suffixes, resolve spelling differences)
  2. Blocking + candidate generation (rapidfuzz, narrows ~37,177 DHIS2 records
     down to the top 5 name-similar candidates within the same region)
  3. LLM final judgment (Gemini) -- given full context (name, zone, woreda,
     facility type) for the unlinked MFR facility and its top candidates,
     decide which candidate is the correct match, or that none is confident
     enough, with a one-sentence reason.

Two modes:
  --mode demo   -> the original 3 pre-validated examples, safe for live TV
                   (this is exactly what was already here, untouched)
  --mode batch  -> runs against ALL real unlinked MFR facilities (dhis2_id
                   is null), resumable, writes incrementally so a crash or
                   Ctrl+C never loses progress.

Usage:
    python llm_facility_linking.py --mode demo
    python llm_facility_linking.py --mode batch --limit 3000 --out facility_linkage_full.csv
    python llm_facility_linking.py --mode batch --limit 30901 --out facility_linkage_full.csv   # the full run
"""
import argparse
import sys
import time

import pandas as pd
from rapidfuzz import process, fuzz
from google import genai
import os
import json

# ---- Config & Client Initialization ----
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MFR_PATH = "mfr_facilities_202607291153.csv"
DHIS2_XLSX_PATH = "dhis2_echis_mfr_facilities.xlsx"


def normalize_region(r):
    if pd.isna(r):
        return None
    r = (
        str(r)
        .replace(" Regional Health Bureau", "")
        .replace(" Region", "")
        .replace(" City Administration", "")
    )
    fixes = {
        "Oromiya": "Oromia",
        "SWE": "South West Ethiopia",
        "Benishangul-Gumuz": "Benishangul Gumuz"
    }
    return fixes.get(r, r)


def load_data():
    mfr = pd.read_csv(MFR_PATH, low_memory=False)
    dhis2 = pd.read_excel(DHIS2_XLSX_PATH, sheet_name="dhis2")
    mfr["region_norm"] = mfr["region"].apply(normalize_region)
    dhis2["region_norm"] = dhis2["regional"].apply(normalize_region)
    return mfr, dhis2


def get_candidates(facility_name, region, dhis2, top_n=5):
    """Stage 2: Blocking + candidate generation via rapidfuzz."""
    pool = dhis2[dhis2["region_norm"] == region]
    if len(pool) == 0:
        return [], pool
    matches = process.extract(
        facility_name,
        pool["name"].dropna().tolist(),
        scorer=fuzz.token_sort_ratio,
        limit=top_n
    )
    return matches, pool


def llm_judge_match(mfr_row, candidates, pool, max_retries=3):
    """Stage 3: LLM final judgment given full spatial context."""
    candidate_details = []
    for name, score, _ in candidates:
        drow = pool[pool["name"] == name].iloc[0]
        candidate_details.append({
            "dhis2_uid": str(drow["uid"]),
            "name": str(drow["name"]),
            "zone": str(drow["zonal"]),
            "woreda": str(drow["wereda"]),
            "facility_type": str(drow["facilitytype"]),
            "name_similarity_score": round(float(score), 1),
        })

    prompt = f"""You are matching a health facility from Ethiopia's Master Facility Registry (MFR) against candidate facilities from the DHIS2 reporting hierarchy. These are two independently maintained government systems with inconsistent naming.

MFR facility (needs a DHIS2 match):
  name: {mfr_row['name']}
  zone: {mfr_row['zone']}
  woreda: {mfr_row['woreda']}
  type: {mfr_row['type']}

Candidate DHIS2 facilities (ranked by name string similarity, which can be misleading -- a lower-scored candidate in the correct zone/woreda is often the right match over a higher-scored one in the wrong location):
{json.dumps(candidate_details, indent=2)}

Decide: which candidate (if any) is the correct match for the MFR facility? Consider name, zone, and woreda together -- do not rely on the similarity score alone. If no candidate is a confident match, say so.

Respond strictly as JSON only, with no markdown formatting:
{{"match_dhis2_uid": "<uid or null>", "confidence": "high|medium|low|none", "reason": "<one sentence>"}}
"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text.strip())
        except Exception as e:
            wait = 2 ** attempt
            print(f"  [retry {attempt+1}/{max_retries}] {e} -- waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("Gemini call failed after retries")


def run_demo_examples():
    """Pre-validated real examples safe for live TV demonstration. UNCHANGED."""
    print("Loading project datasets...")
    mfr, dhis2 = load_data()

    demo_facility_names = [
        "Gendawuha Health Center",   # Clean 100% match
        "Wegedad Health Center",     # Hero example: String score prefers wrong zone!
        "Tesfaye Drug store",        # Correct non-match (Private drug store)
    ]

    results_list = []

    for fname in demo_facility_names:
        sub = mfr[(mfr["name"] == fname) & (mfr["region_norm"] == "Amhara")]
        if len(sub) == 0:
            continue
        row = sub.iloc[0]
        candidates, pool = get_candidates(row["name"], row["region_norm"], dhis2)

        print(f"\n{'='*70}")
        print(f"MFR Facility: {row['name']}  (Zone={row['zone']}, Woreda={row['woreda']})")
        print("Top Candidates (by String Similarity):")
        for name, score, _ in candidates:
            drow = pool[pool["name"] == name].iloc[0]
            print(f"   - {name:<30} (score={score:.1f} | zone={drow['zonal']} | woreda={drow['wereda']})")

        result = llm_judge_match(row, candidates, pool)
        print(f"\nLLM Decision:\n{json.dumps(result, indent=2)}")

        results_list.append({
            "mfr_id": row["id"],
            "mfr_name": row["name"],
            "dhis2_uid": result.get("match_dhis2_uid"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason")
        })

    pd.DataFrame(results_list).to_csv("facility_linkage.csv", index=False)
    print(f"\nCreated facility_linkage.csv successfully!")


def run_batch(limit, out_path, top_n=5):
    """Real batch mode: runs against ALL unlinked MFR facilities, resumable."""
    print("Loading project datasets...")
    mfr, dhis2 = load_data()

    done_ids = set()
    if os.path.exists(out_path):
        prior = pd.read_csv(out_path)
        done_ids = set(prior["mfr_id"])
        print(f"Resuming: {len(done_ids)} facilities already processed in {out_path}")

    unlinked = mfr[mfr["dhis2_id"].isna() & ~mfr["id"].isin(done_ids)]
    unlinked = unlinked.head(limit)
    total_unlinked = mfr["dhis2_id"].isna().sum()
    print(f"Processing {len(unlinked)} unlinked facilities this run (of {total_unlinked} total unlinked)...")

    header_needed = not os.path.exists(out_path)
    processed = 0

    for _, row in unlinked.iterrows():
        candidates, pool = get_candidates(row["name"], row["region_norm"], dhis2, top_n=top_n)

        if len(candidates) == 0:
            result = {"match_dhis2_uid": None, "confidence": "none", "reason": "no candidates in region"}
        else:
            try:
                result = llm_judge_match(row, candidates, pool)
            except Exception as e:
                print(f"  [skip] mfr_id={row['id']} failed after retries: {e}", file=sys.stderr)
                continue

        out_row = pd.DataFrame([{
            "mfr_id": row["id"],
            "mfr_name": row["name"],
            "dhis2_uid": result.get("match_dhis2_uid"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
        }])
        out_row.to_csv(out_path, mode="a", header=header_needed, index=False)
        header_needed = False

        processed += 1
        if processed % 25 == 0:
            print(f"  ...{processed}/{len(unlinked)} done")

    print(f"\nBatch run complete. {processed} facilities processed this run -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "batch"], default="demo")
    ap.add_argument("--limit", type=int, default=3000, help="max unlinked facilities to process (batch mode)")
    ap.add_argument("--out", default="facility_linkage.csv", help="output CSV path (batch mode)")
    ap.add_argument("--top-n", type=int, default=5, help="candidates per facility sent to the LLM")
    args = ap.parse_args()

    if args.mode == "demo":
        run_demo_examples()
    else:
        run_batch(limit=args.limit, out_path=args.out, top_n=args.top_n)