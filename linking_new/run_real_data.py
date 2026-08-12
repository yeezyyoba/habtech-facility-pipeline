#!/usr/bin/env python3
"""
Run the two-stage facility linking pipeline on the REAL MFR and DHIS2 exports,
scoped to the facilities that don't already have a confirmed link.

Why "scoped"?
-------------
The MFR export has a `dhis2_id` column. Cross-checking it against the real
DHIS2 `uid` values shows ~76% of DHIS2 facilities already have a verified,
exact link to an MFR record. Re-running fuzzy matching on those would be
pointless (and would inflate candidate-pair counts for no reason) -- the
actual open problem is just the DHIS2 facilities with no known MFR link,
matched against the MFR facilities that have no known DHIS2 link.

This script:
1. Loads both raw exports.
2. Renames columns to what facility_linker_two_stage.py expects
   (facility_id, facility_name, region, zone, woreda, facility_type,
   owner_type, phone, latitude, longitude).
3. Splits off the already-linked pairs (kept aside, not re-matched).
4. Runs the pipeline only on the unlinked subset.
5. Saves the already-linked pairs alongside the newly inferred ones so you
   have one combined "full linkage" output at the end.

Usage:
    python run_real_data.py \
        --mfr /path/to/mfr_facilities_202607291153.csv \
        --dhis2 /path/to/dhis2_facilities.csv \
        --output-dir ./real_data_results
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from facility_linker_two_stage import FacilityLinkingPipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# MFR and DHIS2 use completely different region-naming conventions
# (e.g. "Harari Region" vs "Harari Regional Health Bureau", and
# "Oromia Region" vs "Oromiya Regional Health Bureau" -- note the spelling
# difference too). Blocking on raw `region` values produces ZERO candidate
# pairs because the strings never match exactly. Both sides are mapped to
# a shared canonical key here before blocking.
#
# NOTE: MFR has "Central Ethiopia Region" and "South Ethiopia Region" with
# no DHIS2 equivalent in this export at all -- those are newer Ethiopian
# regions DHIS2 doesn't yet have separate entries for. Facilities in those
# two MFR regions cannot be region-blocked against DHIS2 and are left
# unmapped (canonical value stays None) -- worth a manual look separately.
REGION_CANONICAL_MAP = {
    # MFR raw value -> canonical key
    'Harari Region': 'harari',
    'Dire Dawa City Administration': 'dire dawa',
    'Tigray Region': 'tigray',
    'Addis Ababa City Administration': 'addis ababa',
    'Oromia Region': 'oromia',
    'Sidama Region': 'sidama',
    'South West Ethiopia Region': 'south west ethiopia',
    'Gambella Region': 'gambella',
    'Benishangul-Gumuz Region': 'benishangul gumuz',
    'Afar Region': 'afar',
    'Somali Region': 'somali',
    'Amhara Region': 'amhara',
    'SNNP Region': 'snnp',
    # 'Central Ethiopia Region' and 'South Ethiopia Region' intentionally
    # left unmapped -- no DHIS2 counterpart exists in this export.

    # DHIS2 raw value -> canonical key
    'Addis Ababa Regional Health Bureau': 'addis ababa',
    'Afar Regional Health Bureau': 'afar',
    'Amhara Regional Health Bureau': 'amhara',
    'Benishangul Gumuz Regional Health Bureau': 'benishangul gumuz',
    'Dire Dawa Regional Health Bureau': 'dire dawa',
    'Gambella Regional Health Bureau': 'gambella',
    'Harari Regional Health Bureau': 'harari',
    'Oromiya Regional Health Bureau': 'oromia',
    'Sidama Regional Health Bureau': 'sidama',
    'SNNP Regional Health Bureau': 'snnp',
    'Somali Regional Health Bureau': 'somali',
    'SWE Regional Health Bureau': 'south west ethiopia',
    'Tigray Regional Health Bureau': 'tigray',
}


def _report_unmapped_regions(df: pd.DataFrame, source_name: str):
    unmapped = df.loc[df['region'].notna() & df['region_canonical'].isna(), 'region'].unique()
    if len(unmapped) > 0:
        logger.warning(
            f"{source_name}: {len(unmapped)} region value(s) have no canonical mapping "
            f"and will be excluded from region-based blocking: {list(unmapped)}"
        )


def load_and_rename_mfr(path: str) -> pd.DataFrame:
    """Load the real MFR export and rename columns to the pipeline's schema."""
    df = pd.read_csv(path, low_memory=False)
    df = df.rename(columns={
        'id': 'facility_id',
        'name': 'facility_name',
        'type': 'facility_type',
        'ownership': 'owner_type',
        'official_phone_number': 'phone',
        # region, zone, woreda, latitude, longitude already match
    })
    df['region_canonical'] = df['region'].map(REGION_CANONICAL_MAP)
    _report_unmapped_regions(df, 'MFR')
    df['region_raw'] = df['region']
    df['region'] = df['region_canonical']
    return df


def load_and_rename_dhis2(path: str) -> pd.DataFrame:
    """
    Load the real DHIS2 export and rename columns to the pipeline's schema.

    Note: DHIS2's `wereda` column does NOT contain real woreda data -- it's
    inconsistently populated with facility-name-like text (verified by
    comparing it against the `name` column). It is intentionally dropped
    rather than mapped, so it doesn't corrupt blocking or comparison.
    """
    df = pd.read_csv(path)
    df = df.rename(columns={
        'uid': 'facility_id',
        'name': 'facility_name',
        'regional': 'region',
        'zonal': 'zone',
        'facilitytype': 'facility_type',
        'ownership': 'owner_type',
    })
    df = df.drop(columns=['wereda'], errors='ignore')
    df['region_canonical'] = df['region'].map(REGION_CANONICAL_MAP)
    _report_unmapped_regions(df, 'DHIS2')
    df['region_raw'] = df['region']
    df['region'] = df['region_canonical']
    return df


def split_linked_unlinked(mfr_df: pd.DataFrame, dhis2_df: pd.DataFrame):
    """
    Split into (already-linked pairs, unlinked MFR subset, unlinked DHIS2 subset)
    using MFR's dhis2_id column cross-checked against real DHIS2 facility_id values.
    """
    valid_dhis2_ids = set(dhis2_df['facility_id'])

    has_valid_link = mfr_df['dhis2_id'].isin(valid_dhis2_ids)

    linked_mfr = mfr_df[has_valid_link].copy()
    unlinked_mfr = mfr_df[~has_valid_link].copy()

    linked_dhis2_ids = set(linked_mfr['dhis2_id'])
    unlinked_dhis2 = dhis2_df[~dhis2_df['facility_id'].isin(linked_dhis2_ids)].copy()

    # Build the "already linked" pairs table in the same shape as the
    # pipeline's final_facility_matches.csv, so it can be concatenated later.
    already_linked = linked_mfr[['facility_id', 'facility_name', 'region_raw', 'dhis2_id']].rename(
        columns={
            'facility_id': 'mfr_id',
            'facility_name': 'mfr_name',
            'region_raw': 'mfr_region',
        }
    )
    already_linked['dhis2_name'] = already_linked['dhis2_id'].map(
        dhis2_df.set_index('facility_id')['facility_name']
    )
    already_linked['dhis2_region'] = already_linked['dhis2_id'].map(
        dhis2_df.set_index('facility_id')['region_raw']
    )
    already_linked['linktransformer_score'] = 1.0
    already_linked['match_source'] = 'existing_dhis2_id'

    logger.info(f"Already linked (verified via dhis2_id): {len(already_linked)} pairs")
    logger.info(f"Unlinked MFR facilities to match: {len(unlinked_mfr)}")
    logger.info(f"Unlinked DHIS2 facilities to match: {len(unlinked_dhis2)}")

    return already_linked, unlinked_mfr.reset_index(drop=True), unlinked_dhis2.reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Run facility linking on real MFR/DHIS2 data.")
    parser.add_argument('--mfr', required=True, help='Path to MFR facilities CSV')
    parser.add_argument('--dhis2', required=True, help='Path to DHIS2 facilities CSV')
    parser.add_argument('--output-dir', default='./real_data_results', help='Output directory')
    parser.add_argument(
        '--full-dataset',
        action='store_true',
        help='Match against ALL facilities instead of just the unlinked subset '
             '(much slower, and re-does work that dhis2_id already gives you for free).'
    )
    args = parser.parse_args()

    logger.info("Loading real MFR and DHIS2 exports...")
    mfr_df = load_and_rename_mfr(args.mfr)
    dhis2_df = load_and_rename_dhis2(args.dhis2)
    logger.info(f"MFR: {len(mfr_df)} rows | DHIS2: {len(dhis2_df)} rows")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    if args.full_dataset:
        logger.info("Running on FULL dataset (--full-dataset flag set)...")
        match_mfr, match_dhis2 = mfr_df, dhis2_df
        already_linked = pd.DataFrame()
    else:
        already_linked, match_mfr, match_dhis2 = split_linked_unlinked(mfr_df, dhis2_df)
        already_linked.to_csv(output_dir / 'already_linked_pairs.csv', index=False)

    pipeline = FacilityLinkingPipeline(output_dir=str(output_dir))

    results = pipeline.run(
        mfr_df=match_mfr,
        dhis2_df=match_dhis2,
        manual_validation_df=None,  # no real validation labels yet -- see note below
        save_intermediate=True
    )

    logger.info("=" * 80)
    logger.info("REAL DATA RUN COMPLETE")
    logger.info("=" * 80)
    logger.info(f"MFR facilities matched against: {results['mfr_count']}")
    logger.info(f"DHIS2 facilities matched against: {results['dhis2_count']}")
    logger.info(f"Candidate pairs (Stage 1): {results['candidate_pairs_count']}")
    logger.info(f"New matches found: {results['final_matches']['total']}")

    if not already_linked.empty:
        new_matches_path = output_dir / 'final_facility_matches.csv'
        if new_matches_path.exists():
            new_matches = pd.read_csv(new_matches_path)
            new_matches['match_source'] = 'inferred'
            combined = pd.concat([already_linked, new_matches], ignore_index=True, sort=False)
            combined_path = output_dir / 'combined_facility_matches.csv'
            combined.to_csv(combined_path, index=False)
            logger.info(f"Combined (existing + newly inferred) matches saved to {combined_path}")
            logger.info(f"Total combined matches: {len(combined)}")

    logger.info(f"\nAll outputs saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    main()
