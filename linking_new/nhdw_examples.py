"""
NHDW Facility Linking Examples: Ethiopia-Specific Use Cases
============================================================
Real-world examples for MFR ↔ DHIS2 ↔ eCHIS linking using the two-stage pipeline

Author: Eyob Nebyou (Habtech)
Context: National Health Data Warehouse (NHDW) at Habtech
Date: Week 2 Deliverable
"""

import pandas as pd
import numpy as np
from pathlib import Path
from facility_linker_two_stage import (
    FacilityLinkingPipeline,
    FacilityPreprocessor,
    RecordLinkageBlocker,
    LinkTransformerMatcher
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# EXAMPLE 1: MFR → DHIS2 Linking (59,917 → 37,177 facilities)
# ============================================================================

def example_1_mfr_to_dhis2():
    """
    Link MFR (Master Facility Registry) to DHIS2 (health facility database).
    
    Expected outcome:
    - ~31k-34k confirmed matches (83-92% of DHIS2)
    - Unmatched DHIS2 facilities are likely private/informal or data quality issues
    - Remaining MFR facilities are likely private or recently added
    """
    
    print("\n" + "="*80)
    print("EXAMPLE 1: MFR ↔ DHIS2 Facility Linking")
    print("="*80)
    
    # Load actual data (replace with your paths)
    logger.info("Loading MFR and DHIS2 data...")
    
    # For demo, we'll create synthetic data matching real patterns
    mfr_df = create_realistic_mfr_data(n=5000)  # Subset of 59,917
    dhis2_df = create_realistic_dhis2_data(n=3500)  # Subset of 37,177
    
    # Most DHIS2 facilities should be in MFR
    # Create ground truth for validation (100-150 manually labeled pairs)
    validation_df = create_validation_data(mfr_df, dhis2_df, sample_size=150)
    
    # Initialize pipeline
    pipeline = FacilityLinkingPipeline(
        output_dir='./results_mfr_dhis2'
    )
    
    # Run complete pipeline
    results = pipeline.run(
        mfr_df=mfr_df,
        dhis2_df=dhis2_df,
        manual_validation_df=validation_df,
        save_intermediate=True
    )
    
    # Analyze results
    logger.info("\n--- MFR → DHIS2 LINKING RESULTS ---")
    logger.info(f"Total matches: {results['final_matches']['total']}")
    logger.info(f"MFR coverage: {results['final_matches']['mfr_coverage']}")
    logger.info(f"DHIS2 coverage: {results['final_matches']['dhis2_coverage']}")
    logger.info(f"Match threshold: {results['match_threshold']:.3f}")
    logger.info(f"Mean LinkTransformer score: {results['linktransformer_score_stats']['mean']:.3f}")
    
    # Identify unmatched DHIS2 facilities (likely private/data quality issues)
    matched_df = pd.read_csv('./results_mfr_dhis2/final_facility_matches.csv')
    dhis2_matched = set(matched_df['dhis2_id'].unique())
    dhis2_unmatched = dhis2_df[~dhis2_df['facility_id'].isin(dhis2_matched)]
    
    logger.info(f"\nUnmatched DHIS2 facilities: {len(dhis2_unmatched)}")
    logger.info("Sample unmatched (likely private/informal):")
    print(dhis2_unmatched[['facility_id', 'facility_name', 'region', 'facility_type']].head(10))
    
    return results


# ============================================================================
# EXAMPLE 2: DHIS2 → eCHIS Linking (37,177 → 8,255 facilities)
# ============================================================================

def example_2_dhis2_to_echis():
    """
    Link DHIS2 facilities to eCHIS (electronic Community Health Information System).
    
    Note: eCHIS covers only primary health care (clinics, health posts).
    Many DHIS2 hospitals/specialized facilities won't match.
    
    Expected outcome:
    - ~7k-8k confirmed matches (85-95% of eCHIS)
    - Remaining DHIS2 = secondary/tertiary hospitals not in eCHIS
    """
    
    print("\n" + "="*80)
    print("EXAMPLE 2: DHIS2 ↔ eCHIS Facility Linking")
    print("="*80)
    
    # Filter DHIS2 to only primary health care (for realistic matching with eCHIS)
    dhis2_df = create_realistic_dhis2_data(n=3500)
    dhis2_phc = dhis2_df[dhis2_df['facility_type'].isin(['HC', 'HP', 'Clinic', 'Dispensary'])]
    
    echis_df = create_realistic_echis_data(n=800)
    
    logger.info(f"DHIS2 Primary Health Care facilities: {len(dhis2_phc)}")
    logger.info(f"eCHIS facilities: {len(echis_df)}")
    
    # Validation sample
    validation_df = create_validation_data(dhis2_phc, echis_df, sample_size=120)
    
    # Pipeline
    pipeline = FacilityLinkingPipeline(
        output_dir='./results_dhis2_echis'
    )
    
    results = pipeline.run(
        mfr_df=dhis2_phc,  # Note: renamed for clarity; actually DHIS2
        dhis2_df=echis_df,  # Note: renamed for clarity; actually eCHIS
        manual_validation_df=validation_df
    )
    
    logger.info("\n--- DHIS2 → eCHIS LINKING RESULTS ---")
    logger.info(f"Matches: {results['final_matches']['total']}")
    logger.info(f"DHIS2 coverage: {results['final_matches']['mfr_coverage']}")
    logger.info(f"eCHIS coverage: {results['final_matches']['dhis2_coverage']}")
    
    return results


# ============================================================================
# EXAMPLE 3: Transitive Linking (MFR → DHIS2 → eCHIS = MFR → eCHIS)
# ============================================================================

def example_3_transitive_linking():
    """
    Chain together two linking results to create indirect links.
    
    MFR → DHIS2 matches + DHIS2 → eCHIS matches = MFR → eCHIS mappings
    
    Useful for: Creating unified facility hierarchy across all three registries
    """
    
    print("\n" + "="*80)
    print("EXAMPLE 3: Transitive Linking (MFR → DHIS2 → eCHIS)")
    print("="*80)
    
    # Load previous results (from Examples 1 & 2)
    logger.info("Loading MFR-DHIS2 and DHIS2-eCHIS matches...")
    
    mfr_dhis2_matches = pd.read_csv('./results_mfr_dhis2/final_facility_matches.csv')
    dhis2_echis_matches = pd.read_csv('./results_dhis2_echis/final_facility_matches.csv')
    
    # Rename columns for clarity
    mfr_dhis2_matches = mfr_dhis2_matches.rename(columns={
        'mfr_id': 'mfr_id',
        'dhis2_id': 'dhis2_id_bridge'  # Bridge table
    })
    
    dhis2_echis_matches = dhis2_echis_matches.rename(columns={
        'mfr_id': 'dhis2_id_bridge',  # Match with bridge
        'dhis2_id': 'echis_id'
    })
    
    # Join on DHIS2 ID
    transitive = mfr_dhis2_matches.merge(
        dhis2_echis_matches[['dhis2_id_bridge', 'echis_id']],
        on='dhis2_id_bridge',
        how='inner'
    )
    
    # Create canonical facility table
    canonical = transitive[[
        'mfr_id', 'dhis2_id_bridge', 'echis_id',
        'mfr_name', 'dhis2_name', 'mfr_region'
    ]].rename(columns={
        'dhis2_id_bridge': 'dhis2_id',
        'mfr_region': 'region'
    })
    
    logger.info(f"\nTransitive matches (MFR → DHIS2 → eCHIS): {len(canonical)}")
    logger.info(f"Facilities with complete triple links: {canonical.dropna().shape[0]}")
    
    # Save canonical table
    canonical.to_csv('./results_canonical_facility_table.csv', index=False)
    logger.info("Saved canonical facility table: results_canonical_facility_table.csv")
    
    return canonical


# ============================================================================
# EXAMPLE 4: Handling Edge Cases (Unmatched Facilities)
# ============================================================================

def example_4_unmatched_analysis():
    """
    Analyze and handle facilities that didn't match.
    
    Categories:
    1. Private/informal (not in MFR)
    2. Recently added to DHIS2 (not yet in MFR)
    3. Data quality issues (name typos, missing fields)
    4. Merged/closed facilities (name changed or facility discontinued)
    """
    
    print("\n" + "="*80)
    print("EXAMPLE 4: Analyzing Unmatched Facilities")
    print("="*80)
    
    # Load matches
    matched_df = pd.read_csv('./results_mfr_dhis2/final_facility_matches.csv')
    
    # Load original data
    mfr_df = pd.read_csv('data/mfr_full.csv')
    dhis2_df = pd.read_csv('data/dhis2_full.csv')
    
    # Find unmatched
    mfr_matched = set(matched_df['mfr_id'].unique())
    dhis2_matched = set(matched_df['dhis2_id'].unique())
    
    mfr_unmatched = mfr_df[~mfr_df['facility_id'].isin(mfr_matched)]
    dhis2_unmatched = dhis2_df[~dhis2_df['facility_id'].isin(dhis2_matched)]
    
    logger.info(f"\nMFR unmatched: {len(mfr_unmatched)} ({100*len(mfr_unmatched)/len(mfr_df):.1f}%)")
    logger.info(f"DHIS2 unmatched: {len(dhis2_unmatched)} ({100*len(dhis2_unmatched)/len(dhis2_df):.1f}%)")
    
    # Analyze unmatched by region
    logger.info("\nUnmatched facilities by region:")
    print(mfr_unmatched.groupby('region').size().sort_values(ascending=False).head(10))
    
    # Analyze unmatched by facility type
    logger.info("\nUnmatched facilities by type:")
    print(mfr_unmatched.groupby('facility_type').size().sort_values(ascending=False))
    
    # Manual review workflow
    logger.info("\n--- Recommend manual review for: ---")
    
    # High-confidence unmatched (likely errors or private)
    dhis2_unmatched_highvalue = dhis2_unmatched[
        dhis2_unmatched['facility_type'].isin(['Hospital', 'Referral Hospital'])
    ]
    logger.info(f"DHIS2 unmatched hospitals: {len(dhis2_unmatched_highvalue)}")
    print(dhis2_unmatched_highvalue[['facility_id', 'facility_name', 'region', 'facility_type']].head(20))
    
    # Save for manual review
    dhis2_unmatched_highvalue.to_csv(
        './results_unmatched_for_review.csv',
        index=False
    )
    logger.info("\nSaved unmatched facilities for manual review: results_unmatched_for_review.csv")
    
    return {
        'mfr_unmatched': mfr_unmatched,
        'dhis2_unmatched': dhis2_unmatched
    }


# ============================================================================
# EXAMPLE 5: Incremental Linking (Adding New Facilities)
# ============================================================================

def example_5_incremental_linking():
    """
    Update linking when new facilities are added to DHIS2.
    
    Use case: New health facilities opened; need to link them to MFR + eCHIS.
    """
    
    print("\n" + "="*80)
    print("EXAMPLE 5: Incremental Linking for New Facilities")
    print("="*80)
    
    # Assume we have new facilities from a recent Kafka message
    new_facilities = pd.DataFrame({
        'facility_id': ['DHIS2_NEW_001', 'DHIS2_NEW_002'],
        'facility_name': [
            'Addis Ketema Health Center',
            'Nifas Silk Sub-District Hospital'
        ],
        'region': ['Addis Ababa', 'Addis Ababa'],
        'woreda': ['Addis Ketema', 'Nifas Silk'],
        'zone': ['Central', 'Central'],
        'facility_type': ['HC', 'Hospital'],
        'phone': ['0111234567', '0111234568']
    })
    
    # Load full MFR
    mfr_df = pd.read_csv('data/mfr_full.csv')
    
    logger.info(f"Linking {len(new_facilities)} new DHIS2 facilities to MFR...")
    
    # Pipeline: Use existing match threshold (no calibration needed)
    pipeline = FacilityLinkingPipeline(
        output_dir='./results_new_facilities'
    )
    
    results = pipeline.run(
        mfr_df=mfr_df,
        dhis2_df=new_facilities,
        match_threshold=0.82,  # Use previously calibrated threshold
        save_intermediate=False
    )
    
    # Load matches
    new_matches = pd.read_csv('./results_new_facilities/final_facility_matches.csv')
    
    logger.info(f"\nMatched {len(new_matches)} new facilities:")
    print(new_matches[['mfr_id', 'mfr_name', 'dhis2_id', 'dhis2_name', 'linktransformer_score']])
    
    # Update canonical table
    # INSERT INTO facility_canonical VALUES (new_matches...)
    
    return new_matches


# ============================================================================
# HELPER FUNCTIONS: Create Realistic Test Data
# ============================================================================

def create_realistic_mfr_data(n=1000):
    """Create realistic MFR sample with Ethiopia-specific facility names."""
    
    regions = [
        'Addis Ababa', 'Adis Ababa', 'AA',  # Spelling variations
        'SNNPR', 'Southern Nations', 'South',
        'Oromia', 'Oromiya',
        'Amhara',
        'Tigray',
        'Dire Dawa'
    ]
    
    woredas = [
        'Bole', 'Kirkos', 'Nifas Silk', 'Addis Ketema', 'Arada', 'Lideta',
        'Hawassa', 'Hosaena', 'Butajira',
        'Adama', 'Dukem', 'Modjo',
        'Bahir Dar', 'Gondar',
        'Mekelle'
    ]
    
    facility_names = [
        'Health Center', 'HC', 'Health Post', 'HP',
        'Hospital', 'Referral Hospital', 'Gen. Hospital', 'Gen Hospital',
        'Clinic', 'Dispensary',
        'Primary Health Care', 'PHC',
        'Community Health', 'District Hospital'
    ]
    
    # Generate records
    records = []
    for i in range(n):
        records.append({
            'facility_id': f'MFR_{i+1:06d}',
            'facility_name': f"{np.random.choice(woredas)} {np.random.choice(facility_names)}",
            'region': np.random.choice(regions),
            'zone': f"Zone {np.random.randint(1, 6)}",
            'woreda': np.random.choice(woredas),
            'facility_type': np.random.choice(['HC', 'HP', 'Hospital', 'Clinic']),
            'phone': f"09{np.random.randint(1, 9)}{np.random.randint(10000000, 99999999)}",
            'latitude': float(np.random.uniform(3, 15)),
            'longitude': float(np.random.uniform(33, 48))
        })
    
    return pd.DataFrame(records)


def create_realistic_dhis2_data(n=1000):
    """Create DHIS2 sample with name variations matching MFR."""
    
    # Start with MFR-like data but with variations
    mfr_sample = create_realistic_mfr_data(int(n * 0.8))
    
    # Rename IDs
    mfr_sample['facility_id'] = mfr_sample['facility_id'].str.replace('MFR_', 'DHIS2_')
    
    # Introduce variations
    mfr_sample['facility_name'] = mfr_sample['facility_name'].apply(
        lambda x: x.replace('HC', 'Health Center')
        .replace('HP', 'Health Post')
        .replace('Hosp', 'Hospital')
        if np.random.random() > 0.5 else x
    )
    
    # Add some unique DHIS2-only facilities (private/NGO)
    unique_dhis2 = {
        'facility_id': [f'DHIS2_{n+1+i:06d}' for i in range(int(n * 0.2))],
        'facility_name': [f"Private Clinic {i}" for i in range(int(n * 0.2))],
        'region': np.random.choice(['Addis Ababa', 'Oromia'], int(n * 0.2)),
        'zone': [f"Zone {np.random.randint(1, 6)}" for _ in range(int(n * 0.2))],
        'woreda': np.random.choice(['Bole', 'Kirkos', 'Nifas Silk'], int(n * 0.2)),
        'facility_type': ['Clinic'] * int(n * 0.2),
        'phone': [f"09{np.random.randint(1, 9)}{np.random.randint(10000000, 99999999)}" for _ in range(int(n * 0.2))],
        'latitude': np.random.uniform(3, 15, int(n * 0.2)),
        'longitude': np.random.uniform(33, 48, int(n * 0.2))
    }
    
    dhis2_full = pd.concat([
        mfr_sample,
        pd.DataFrame(unique_dhis2)
    ], ignore_index=True)
    
    return dhis2_full


def create_realistic_echis_data(n=500):
    """Create eCHIS sample (primary health care facilities only)."""
    
    records = []
    for i in range(n):
        records.append({
            'facility_id': f'ECHIS_{i+1:06d}',
            'facility_name': f"{np.random.choice(['Bole', 'Kirkos', 'Nifas Silk', 'Hawassa'])} Health Center",
            'region': np.random.choice(['Addis Ababa', 'SNNPR']),
            'zone': f"Zone {np.random.randint(1, 3)}",
            'woreda': np.random.choice(['Bole', 'Hawassa']),
            'facility_type': 'HC',
            'phone': f"09{np.random.randint(1, 9)}{np.random.randint(10000000, 99999999)}",
            'latitude': float(np.random.uniform(5, 9)),
            'longitude': float(np.random.uniform(38, 40))
        })
    
    return pd.DataFrame(records)


def create_validation_data(df_a, df_b, sample_size=150):
    """
    Create validation data by stratified sampling.
    
    Samples from high/medium/low confidence buckets.
    """
    
    # For demo: assume first N matches are correct, rest are not
    n_true_matches = min(len(df_a), len(df_b)) // 2
    
    validation = []
    
    # True matches
    for i in range(min(n_true_matches, sample_size // 2)):
        validation.append({
            'mfr_id': df_a.iloc[i]['facility_id'],
            'dhis2_id': df_b.iloc[i]['facility_id'],
            'label': 1
        })
    
    # False matches
    for i in range(sample_size - len(validation)):
        idx_a = np.random.randint(0, len(df_a))
        idx_b = np.random.randint(n_true_matches, len(df_b))
        validation.append({
            'mfr_id': df_a.iloc[idx_a]['facility_id'],
            'dhis2_id': df_b.iloc[idx_b]['facility_id'],
            'label': 0
        })
    
    return pd.DataFrame(validation)


# ============================================================================
# MAIN: Run All Examples
# ============================================================================

if __name__ == "__main__":
    
    print("\n" + "="*80)
    print("NHDW FACILITY LINKING EXAMPLES")
    print("Ethiopia National Health Data Warehouse (Habtech)")
    print("="*80)
    
    # Uncomment to run individual examples
    
    # Example 1: MFR → DHIS2
    # results_1 = example_1_mfr_to_dhis2()
    
    # Example 2: DHIS2 → eCHIS
    # results_2 = example_2_dhis2_to_echis()
    
    # Example 3: Transitive linking
    # canonical = example_3_transitive_linking()
    
    # Example 4: Unmatched analysis
    # unmatched = example_4_unmatched_analysis()
    
    # Example 5: Incremental linking
    # new_matches = example_5_incremental_linking()
    
    print("\n" + "="*80)
    print("To run examples, uncomment the desired example in __main__")
    print("="*80)
