#!/usr/bin/env python3
"""
Interactive Demo: Two-Stage Facility Linking Pipeline
======================================================
Run this script to see the complete pipeline in action with sample data.

Usage:
    python demo_linker.py

This will:
1. Create realistic sample MFR, DHIS2, and validation data
2. Run the complete two-stage linking pipeline
3. Display results and visualizations
4. Save output files for inspection
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add current directory to path to import facility_linker
sys.path.insert(0, str(Path(__file__).parent))

from facility_linker_two_stage import FacilityLinkingPipeline


# ============================================================================
# SAMPLE DATA GENERATION
# ============================================================================

def create_demo_mfr_data(n=500):
    """
    Create realistic MFR (Master Facility Registry) sample data.
    
    Representative of actual Ethiopian health facilities with:
    - Regional variations
    - Name variations (HC vs Health Center)
    - Realistic phone numbers
    - Geographic coordinates
    """
    
    np.random.seed(42)
    
    regions = {
        'Addis Ababa': ['Bole', 'Kirkos', 'Nifas Silk', 'Addis Ketema', 'Arada', 'Lideta'],
        'SNNPR': ['Hawassa', 'Hosaena', 'Butajira', 'Arba Minch'],
        'Oromia': ['Adama', 'Dukem', 'Modjo', 'Bishoftu', 'Dire Dawa'],
        'Amhara': ['Bahir Dar', 'Dessie', 'Gondar', 'Mekelle'],
    }
    
    facility_prefixes = [
        'Addis Ababa',
        'Hawassa',
        'Dire Dawa',
        'Bole',
        'Kirkos',
        'Nifas Silk',
        'Hosaena',
        'Butajira',
        'Adama',
        'Dukem',
        'Modjo',
        'Bahir Dar',
        'Dessie',
        'Gondar',
    ]
    
    facility_types = [
        'Health Center',
        'HC',
        'Health Post',
        'HP',
        'Hospital',
        'Referral Hospital',
        'General Hospital',
        'Clinic',
        'Dispensary',
    ]
    
    records = []
    region_list = list(regions.keys())
    
    for i in range(n):
        region = np.random.choice(region_list)
        woreda = np.random.choice(regions[region])
        prefix = np.random.choice(facility_prefixes)
        facility_type = np.random.choice(facility_types)
        
        facility_id = f'MFR_{i+1:06d}'
        facility_name = f"{prefix} {facility_type}"
        
        # Realistic coordinates for Ethiopia
        latitude = float(np.random.uniform(3, 15))
        longitude = float(np.random.uniform(33, 48))
        
        phone = f"09{np.random.randint(1, 9)}{np.random.randint(10000000, 99999999):08d}"
        
        records.append({
            'facility_id': facility_id,
            'facility_name': facility_name,
            'region': region,
            'woreda': woreda,
            'zone': f"Zone {np.random.randint(1, 6)}",
            'facility_type': facility_type,
            'phone': phone,
            'latitude': latitude,
            'longitude': longitude,
            'owner_type': np.random.choice(['Public', 'Private', 'NGO']),
        })
    
    return pd.DataFrame(records)


def create_demo_dhis2_data(mfr_df, private_ratio=0.15):
    """
    Create DHIS2 data by:
    1. Taking ~85% of MFR facilities and introducing name variations
    2. Adding ~15% unique private/NGO facilities not in MFR
    
    This simulates real-world scenario where DHIS2 has some unique facilities.
    """
    
    np.random.seed(42)
    
    # Sample from MFR (~85%)
    n_from_mfr = int(len(mfr_df) * (1 - private_ratio))
    mfr_sample = mfr_df.sample(n=n_from_mfr, random_state=42).copy()
    
    # Rename IDs
    mfr_sample['facility_id'] = mfr_sample['facility_id'].str.replace('MFR_', 'DHIS2_')
    
    # Introduce name variations (simulate data entry variations)
    def introduce_variation(name):
        """Randomly apply variations to facility names."""
        if np.random.random() > 0.5:
            # Expand abbreviations
            name = name.replace('HC', 'Health Center')
            name = name.replace('HP', 'Health Post')
            name = name.replace('Hosp', 'Hospital')
        
        if np.random.random() > 0.7:
            # Add small spelling errors
            words = name.split()
            if len(words) > 0 and len(words[0]) > 2:
                words[0] = words[0][:-1]  # Remove last letter
            name = ' '.join(words)
        
        return name
    
    mfr_sample['facility_name'] = mfr_sample['facility_name'].apply(introduce_variation)
    
    # Add unique DHIS2 facilities (private/NGO)
    n_unique = int(len(mfr_df) * private_ratio)
    unique_records = []
    
    for i in range(n_unique):
        unique_records.append({
            'facility_id': f'DHIS2_{len(mfr_df)+1+i:06d}',
            'facility_name': f"Private Clinic {i+1}",
            'region': np.random.choice(mfr_df['region'].unique()),
            'woreda': np.random.choice(mfr_df['woreda'].unique()),
            'zone': f"Zone {np.random.randint(1, 6)}",
            'facility_type': 'Clinic',
            'phone': f"09{np.random.randint(1, 9)}{np.random.randint(10000000, 99999999):08d}",
            'latitude': float(np.random.uniform(3, 15)),
            'longitude': float(np.random.uniform(33, 48)),
            'owner_type': 'Private',
        })
    
    unique_df = pd.DataFrame(unique_records)
    
    # Combine
    dhis2_full = pd.concat([mfr_sample, unique_df], ignore_index=True)
    
    return dhis2_full.reset_index(drop=True)


def create_demo_validation_data(mfr_df, dhis2_df, sample_size=150):
    """
    Create manual validation labels for threshold calibration.
    
    Simulates manual review where domain experts label ~150 facility pairs as match/no-match.
    """
    
    np.random.seed(42)
    
    validation = []
    
    # Strategy: Label pairs that should match based on similarity
    mfr_records = mfr_df.to_dict('records')
    dhis2_records = dhis2_df.to_dict('records')
    
    # Sample pairs
    for _ in range(sample_size):
        if np.random.random() > 0.7:
            # True match: facilities from same woreda/region with similar names
            woreda = np.random.choice(mfr_df['woreda'].unique())
            mfr_candidates = [r for r in mfr_records if r['woreda'] == woreda]
            dhis2_candidates = [r for r in dhis2_records if r['woreda'] == woreda]
            
            if mfr_candidates and dhis2_candidates:
                mfr_rec = np.random.choice([r for r in mfr_candidates])
                dhis2_rec = np.random.choice([r for r in dhis2_candidates])
                
                validation.append({
                    'mfr_id': mfr_rec['facility_id'],
                    'dhis2_id': dhis2_rec['facility_id'],
                    'label': 1  # Match
                })
        else:
            # Non-match: random facilities from different woredas
            mfr_rec = np.random.choice(mfr_records)
            dhis2_rec = np.random.choice(dhis2_records)
            
            # Ensure different woreda
            while dhis2_rec['woreda'] == mfr_rec['woreda']:
                dhis2_rec = np.random.choice(dhis2_records)
            
            validation.append({
                'mfr_id': mfr_rec['facility_id'],
                'dhis2_id': dhis2_rec['facility_id'],
                'label': 0  # No match
            })
    
    return pd.DataFrame(validation)


# ============================================================================
# INTERACTIVE DEMO
# ============================================================================

def print_section(title):
    """Pretty print section header."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def print_dataframe_summary(df, title):
    """Print formatted dataframe summary."""
    print(f"\n{title}:")
    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"\n  Sample records:")
    print(df.head(3).to_string(index=False))


def run_demo():
    """Run the complete interactive demo."""
    
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*15 + "FACILITY LINKING PIPELINE DEMO" + " "*33 + "║")
    print("║" + " "*10 + "Two-Stage: recordlinkage + LinkTransformer" + " "*25 + "║")
    print("║" + " "*22 + "Ethiopia NHDW (Habtech)" + " "*34 + "║")
    print("╚" + "="*78 + "╝")
    
    # -------- STEP 1: GENERATE SAMPLE DATA --------
    print_section("STEP 1: Generating Sample Data")
    
    logger.info("Creating MFR sample data (500 facilities)...")
    mfr_df = create_demo_mfr_data(n=500)
    print_dataframe_summary(mfr_df, "MFR (Master Facility Registry)")
    
    logger.info("Creating DHIS2 sample data (derived from MFR with variations)...")
    dhis2_df = create_demo_dhis2_data(mfr_df, private_ratio=0.15)
    print_dataframe_summary(dhis2_df, "DHIS2 (Health Facility Database)")
    
    logger.info("Creating manual validation labels for threshold calibration...")
    validation_df = create_demo_validation_data(mfr_df, dhis2_df, sample_size=150)
    print_dataframe_summary(validation_df, "Manual Validation Labels (150 pairs)")
    
    print(f"\nValidation label distribution:")
    print(validation_df['label'].value_counts().to_string())
    
    # -------- STEP 2: SAVE SAMPLE DATA --------
    print_section("STEP 2: Saving Sample Data")
    
    demo_dir = Path('./demo_data')
    demo_dir.mkdir(exist_ok=True)
    
    mfr_path = demo_dir / 'mfr_sample.csv'
    dhis2_path = demo_dir / 'dhis2_sample.csv'
    validation_path = demo_dir / 'validation_sample.csv'
    
    mfr_df.to_csv(mfr_path, index=False)
    dhis2_df.to_csv(dhis2_path, index=False)
    validation_df.to_csv(validation_path, index=False)
    
    logger.info(f"✓ Saved MFR to {mfr_path}")
    logger.info(f"✓ Saved DHIS2 to {dhis2_path}")
    logger.info(f"✓ Saved validation to {validation_path}")
    
    # -------- STEP 3: INITIALIZE PIPELINE --------
    print_section("STEP 3: Initializing Facility Linking Pipeline")
    
    output_dir = './demo_results'
    logger.info(f"Pipeline output directory: {output_dir}")
    
    pipeline = FacilityLinkingPipeline(output_dir=output_dir)
    logger.info("✓ Pipeline initialized")
    
    # -------- STEP 4: RUN PIPELINE --------
    print_section("STEP 4: Running Two-Stage Linking Pipeline")
    
    print("\nStarting pipeline execution...\n")
    
    results = pipeline.run(
        mfr_df=mfr_df,
        dhis2_df=dhis2_df,
        manual_validation_df=validation_df,
        save_intermediate=True
    )
    
    # -------- STEP 5: DISPLAY RESULTS --------
    print_section("STEP 5: Pipeline Results")
    
    print("Summary Statistics:")
    print(f"  Total MFR facilities:        {results['mfr_count']:,}")
    print(f"  Total DHIS2 facilities:      {results['dhis2_count']:,}")
    print(f"  Candidate pairs (Stage 1):   {results['candidate_pairs_count']:,}")
    print(f"  Reduction ratio:             {100*results['candidate_pairs_count']/(results['mfr_count']*results['dhis2_count']):.2f}%")
    
    print(f"\nStage 2 Scoring Statistics:")
    print(f"  Mean score:                  {results['linktransformer_score_stats']['mean']:.3f}")
    print(f"  Median score:                {results['linktransformer_score_stats']['median']:.3f}")
    print(f"  Std dev:                     {results['linktransformer_score_stats']['std']:.3f}")
    print(f"  Score range:                 [{results['linktransformer_score_stats']['min']:.3f}, {results['linktransformer_score_stats']['max']:.3f}]")
    
    print(f"\nThreshold Calibration:")
    if 'calibration' in results:
        cal = results['calibration']
        print(f"  Optimal threshold:           {results['match_threshold']:.3f}")
        print(f"  Precision:                   {cal['precision']:.3f}")
        print(f"  Recall:                      {cal['recall']:.3f}")
        print(f"  F1-Score:                    {cal['f1']:.3f}")
    else:
        print(f"  Using default threshold:     {results['match_threshold']:.3f}")
    
    print(f"\nFinal Matches:")
    print(f"  Total matches:               {results['final_matches']['total']}")
    print(f"  MFR coverage:                {results['final_matches']['mfr_coverage']}")
    print(f"  DHIS2 coverage:              {results['final_matches']['dhis2_coverage']}")
    
    # -------- STEP 6: LOAD AND DISPLAY FINAL MATCHES --------
    print_section("STEP 6: Inspecting Final Matches")
    
    matches_file = Path(output_dir) / 'final_facility_matches.csv'
    if matches_file.exists():
        matches_df = pd.read_csv(matches_file)
        
        print(f"Final matches file: {matches_file}")
        print(f"\nTop 10 highest confidence matches (by LinkTransformer score):")
        print()
        
        top_matches = matches_df.nlargest(10, 'linktransformer_score')[
            ['mfr_name', 'dhis2_name', 'mfr_region', 'linktransformer_score']
        ]
        
        for idx, row in top_matches.iterrows():
            print(f"  [{row['linktransformer_score']:.3f}]  {row['mfr_name'][:30]:30s} → {row['dhis2_name'][:30]:30s}  ({row['mfr_region']})")
        
        print(f"\n\nLowest confidence matches (by LinkTransformer score):")
        print()
        
        low_matches = matches_df.nsmallest(10, 'linktransformer_score')[
            ['mfr_name', 'dhis2_name', 'mfr_region', 'linktransformer_score']
        ]
        
        for idx, row in low_matches.iterrows():
            print(f"  [{row['linktransformer_score']:.3f}]  {row['mfr_name'][:30]:30s} → {row['dhis2_name'][:30]:30s}  ({row['mfr_region']})")
    
    # -------- STEP 7: IDENTIFY UNMATCHED FACILITIES --------
    print_section("STEP 7: Unmatched Facilities Analysis")
    
    if matches_file.exists():
        matches_df = pd.read_csv(matches_file)
        dhis2_matched = set(matches_df['dhis2_id'].unique())
        dhis2_unmatched = dhis2_df[~dhis2_df['facility_id'].isin(dhis2_matched)]
        
        print(f"Unmatched DHIS2 facilities: {len(dhis2_unmatched)} ({100*len(dhis2_unmatched)/len(dhis2_df):.1f}%)")
        print(f"\nThese are likely private/NGO facilities not in MFR:")
        print()
        print(dhis2_unmatched[['facility_id', 'facility_name', 'region', 'owner_type']].head(10).to_string(index=False))
    
    # -------- STEP 8: OUTPUT FILES SUMMARY --------
    print_section("STEP 8: Output Files Summary")
    
    output_path = Path(output_dir)
    if output_path.exists():
        output_files = list(output_path.glob('*'))
        
        print(f"Results saved to: {output_path.absolute()}\n")
        print("Output files:")
        
        file_descriptions = {
            'final_facility_matches.csv': '→ MAIN OUTPUT: Your linked facilities',
            'stage1_blocking_features.csv': '→ Blocking stage scores (string similarity)',
            'stage2_linktransformer_scores.csv': '→ All candidate pairs with LinkTransformer scores',
            'mfr_preprocessed.csv': '→ MFR after preprocessing',
            'dhis2_preprocessed.csv': '→ DHIS2 after preprocessing',
            'pipeline_summary.json': '→ Pipeline metadata and metrics',
            'threshold_calibration.json': '→ Threshold optimization results',
            'precision_recall_curve.png': '→ Precision-Recall visualization',
            'confusion_matrix.png': '→ Confusion matrix at optimal threshold',
            'facility_linker.log': '→ Detailed execution log',
        }
        
        for f in sorted(output_files):
            desc = file_descriptions.get(f.name, '→ Output file')
            size = f.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            print(f"  ✓ {f.name:40s} ({size_str:8s})  {desc}")
    
    # -------- STEP 9: NEXT STEPS --------
    print_section("STEP 9: Next Steps")
    
    print("""
1. INSPECT RESULTS
   - Open demo_results/final_facility_matches.csv in Excel
   - Review high and low confidence matches
   - Identify patterns in unmatched facilities

2. REFINE THRESHOLD
   - Look at precision_recall_curve.png
   - Consider adjusting threshold based on your use case
   - Run pipeline again with match_threshold=0.XX

3. VALIDATE MATCHES
   - Sample 50-100 matches for manual verification
   - Calculate actual precision/recall with domain experts
   - Adjust blocking strategy if needed

4. SCALE TO PRODUCTION
   - Use your full MFR, DHIS2, and eCHIS datasets
   - Integrate with Kafka/Debezium for streaming updates
   - Store results in ClickHouse canonical facility table
   - Expose via Superset/Grafana dashboards

5. INTEGRATE WITH NHDW
   - Create dbt models for canonical facility table
   - Set up Keycloak SSO access control
   - Configure MinIO versioning for facility hierarchies
   - Monitor matching quality metrics over time

For detailed documentation, see: FACILITY_LINKER_GUIDE.md
For code examples, see: nhdw_examples.py
    """)
    
    print_section("Demo Complete!")
    print(f"✓ Pipeline executed successfully")
    print(f"✓ Results saved to: {output_path.absolute()}")
    print(f"✓ Start time: {results['timestamp']}\n")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    try:
        run_demo()
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
