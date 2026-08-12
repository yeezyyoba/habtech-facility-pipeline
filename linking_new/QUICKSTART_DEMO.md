# Quick Start: Run the Facility Linker Demo in 5 Minutes

This guide gets you from zero to seeing facility matches in 5 minutes.

---

## Prerequisites

- Python 3.8+
- pip
- 4GB RAM minimum

---

## Installation (2 minutes)

### Step 1: Create virtual environment

```bash
python3 -m venv linker_env
source linker_env/bin/activate  # On Windows: linker_env\Scripts\activate
```

### Step 2: Install dependencies

```bash
pip install -r requirements_linker.txt
```

**Note:** First run may take 2-3 minutes as it downloads pretrained models (~500MB).

### Verify Installation

```bash
python3 -c "from sentence_transformers import CrossEncoder; print('✓ Ready to run demo')"
```

---

## Run the Demo (3 minutes)

### Execute demo script

```bash
python demo_linker.py
```

You should see output like:

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    FACILITY LINKING PIPELINE DEMO                          ║
║              Two-Stage: recordlinkage + LinkTransformer                    ║
║                    Ethiopia NHDW (Habtech)                                 ║
╚════════════════════════════════════════════════════════════════════════════╝

================================================================================
  STEP 1: Generating Sample Data
================================================================================

2024-08-12 14:30:45 - INFO - Creating MFR sample data (500 facilities)...

MFR (Master Facility Registry):
  Shape: (500, 10)
  Columns: ['facility_id', 'facility_name', 'region', 'woreda', 'zone', 'facility_type', 'phone', 'latitude', 'longitude', 'owner_type']

  Sample records:
   facility_id             facility_name region woreda           zone facility_type        phone   latitude  longitude owner_type
       MFR_000001        Addis Ababa HC Addis Ababa    Bole  Zone 3  Health Center 0912345678   9.033333  38.748333    Public
       MFR_000002  Hawassa Referral Hospital     SNNPR Hawassa  Zone 1  Hospital      0911234567   5.027778  38.474722    NGO
       MFR_000003   Dire Dawa Dispensary Dire Dawa Dire Dawa  Zone 2  Dispensary    0922222222   9.582222  41.866667    Public

...
================================================================================
  STEP 4: Running Two-Stage Linking Pipeline
================================================================================

Starting pipeline execution...

2024-08-12 14:32:10 - INFO - ================================================================================
2024-08-12 14:32:10 - INFO - STARTING TWO-STAGE FACILITY LINKING PIPELINE
2024-08-12 14:32:10 - INFO - ================================================================================
2024-08-12 14:32:10 - INFO - --- STAGE 0: PREPROCESSING ---
2024-08-12 14:32:12 - INFO - Preprocessed 500 facility records
...
```

The demo will take 2-4 minutes depending on your hardware.

---

## View Results

When the demo completes, you'll see:

```
================================================================================
  STEP 5: Pipeline Results
================================================================================

Summary Statistics:
  Total MFR facilities:        500
  Total DHIS2 facilities:      575
  Candidate pairs (Stage 1):   45,234
  Reduction ratio:             15.72%

Stage 2 Scoring Statistics:
  Mean score:                  0.847
  Median score:                0.863
  Std dev:                     0.082
  Score range:                 [0.502, 0.998]

Threshold Calibration:
  Optimal threshold:           0.820
  Precision:                   0.912
  Recall:                      0.874
  F1-Score:                    0.893

Final Matches:
  Total matches:               421
  MFR coverage:                84.2%
  DHIS2 coverage:              73.2%

================================================================================
  STEP 6: Inspecting Final Matches
================================================================================

Top 10 highest confidence matches (by LinkTransformer score):

  [0.998]  Addis Ababa Health Center      → Addis Ababa HC                 (Addis Ababa)
  [0.995]  Hawassa Referral Hospital      → Hawasa General Hospital        (SNNPR)
  [0.992]  Dire Dawa Clinic              → Dire Dawa Dispensary           (Dire Dawa)
  ...
```

---

## Check Output Files

Three main directories are created:

### 1. `demo_data/` - Sample datasets

```
demo_data/
  ├── mfr_sample.csv              (500 facilities)
  ├── dhis2_sample.csv            (575 facilities)
  └── validation_sample.csv       (150 labeled pairs)
```

### 2. `demo_results/` - Pipeline outputs

```
demo_results/
  ├── final_facility_matches.csv           ← MAIN RESULTS
  ├── stage1_blocking_features.csv         (blocking scores)
  ├── stage2_linktransformer_scores.csv    (all candidates + scores)
  ├── precision_recall_curve.png           (visualization)
  ├── confusion_matrix.png                 (validation metrics)
  ├── pipeline_summary.json                (metadata)
  └── facility_linker.log                  (detailed log)
```

### 3. View Results in Excel

```bash
# Open final matches in spreadsheet (Mac/Linux)
open demo_results/final_facility_matches.csv

# Or on Windows
start demo_results/final_facility_matches.csv
```

**Columns in final_facility_matches.csv:**
- `mfr_id` : Facility ID from MFR
- `mfr_name` : Facility name from MFR
- `mfr_region` : Region from MFR
- `dhis2_id` : Facility ID from DHIS2
- `dhis2_name` : Facility name from DHIS2
- `linktransformer_score` : Semantic similarity score (0.0-1.0)
  - > 0.90 = very confident match
  - 0.80-0.90 = confident match
  - < 0.80 = marginal match (threshold dependent)

---

## Understanding the Results

### Score Distribution

Check `precision_recall_curve.png` to see:
- How precision/recall changes with threshold
- Where the optimal threshold was chosen
- Tradeoff between matching more facilities vs. false positives

### Confusion Matrix

Check `confusion_matrix.png` to see:
- **True Positives (TP)** = Correctly matched pairs
- **False Positives (FP)** = Incorrectly matched pairs (Type 1 error)
- **False Negatives (FN)** = Missed matches (Type 2 error)
- **True Negatives (TN)** = Correctly identified non-matches

### Stage 1 vs Stage 2

- **stage1_blocking_features.csv**: Traditional string similarity scores
  - Shows which pairs were generated as candidates
  - Useful for understanding why Stage 2 was needed
  
- **stage2_linktransformer_scores.csv**: Deep learning semantic scores
  - All candidates scored by pretrained model
  - More accurate for fuzzy/multilingual matches

---

## Next: Try With Your Data

Once the demo works, use your actual data:

```python
import pandas as pd
from facility_linker_two_stage import FacilityLinkingPipeline

# Load YOUR data
mfr = pd.read_csv('your_mfr.csv')
dhis2 = pd.read_csv('your_dhis2.csv')
validation = pd.read_csv('your_manual_validation.csv')  # Optional

# Run pipeline
pipeline = FacilityLinkingPipeline(output_dir='./my_results')
results = pipeline.run(
    mfr_df=mfr,
    dhis2_df=dhis2,
    manual_validation_df=validation
)

print(f"Matched {results['final_matches']['total']} facilities")
```

**Input data format required:**
- `facility_id` : Unique identifier
- `facility_name` : Facility name
- `region` : Administrative region
- `woreda` : District/woreda
- `zone` : Zone (optional but recommended)

See `FACILITY_LINKER_GUIDE.md` for detailed format specifications.

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"

**Solution:**
```bash
pip install -r requirements_linker.txt
```

### Issue: "CUDA out of memory"

**Solution:** Use CPU instead

Edit `demo_linker.py` line ~5:
```python
MODEL_CONFIG['device'] = 'cpu'
```

### Issue: Very slow (>5 minutes)

**Solution:** Reduce sample size

Edit `demo_linker.py` line ~300:
```python
mfr_df = create_demo_mfr_data(n=100)  # Instead of 500
dhis2_df = create_demo_dhis2_data(mfr_df, private_ratio=0.15)
```

### Issue: "facility_linker_two_stage.py not found"

**Solution:** Ensure you're running demo from the correct directory:

```bash
cd /path/to/facility_linker_files
python demo_linker.py
```

---

## What the Demo Shows

✅ **Stage 1: Blocking**
- Phonetic indexing reduces 500 × 575 = 287,500 candidates to ~45k
- 15% reduction in candidate space (typical: 0.1-5%)

✅ **Stage 2: Semantic Matching**
- LinkTransformer scores 45k candidates using deep learning
- Catches fuzzy matches: "Hawassa Referral" ↔ "Hawasa General"
- Handles abbreviations: "HC" ↔ "Health Center"

✅ **Threshold Calibration**
- Automatic threshold optimization using manual labels
- F1-score balances precision (avoid false positives) and recall (catch true matches)
- Shows precision-recall tradeoff visually

✅ **Quality Metrics**
- Confusion matrix at optimal threshold
- Coverage statistics (% of facilities matched)
- Score distribution analysis

---

## Understanding Scores

Example output:

```
[0.998]  Addis Ababa Health Center      → Addis Ababa HC
         ^ This is the LinkTransformer score (0.0-1.0)
         
         Names are nearly identical → very high score
```

```
[0.756]  Hosaena Referral Hospital      → Hosaena Clinic
         ^ Borderline match (below 0.82 threshold)
         
         Different facility types (Hospital vs Clinic) → lower score
         Might be legitimate match or false positive → needs review
```

**Guidelines:**
- **0.95+** = Almost certainly same facility
- **0.85-0.95** = Very likely same facility
- **0.80-0.85** = Probably same facility (depends on threshold)
- **0.70-0.80** = Uncertain; requires manual review
- **<0.70** = Probably different facilities

---

## Advanced: Inspect Intermediate Stages

```bash
# See what Stage 1 blocking found
head -20 demo_results/stage1_blocking_features.csv

# See all Stage 2 scores (before filtering by threshold)
wc -l demo_results/stage2_linktransformer_scores.csv

# See preprocessing transformations
head -10 demo_results/mfr_preprocessed.csv
```

---

## Next Steps

1. ✅ **Run demo** (you are here)
2. **Review results** in Excel/CSV
3. **Understand outputs** (see guide above)
4. **Try with your data** (modify demo_linker.py or use FACILITY_LINKER_GUIDE.md)
5. **Calibrate threshold** with manual validation labels
6. **Integrate with NHDW** (see advanced section in main guide)

---

## Questions?

- **How do I use my own data?** See "Next: Try With Your Data" section above
- **What if matching quality is poor?** See threshold calibration section in FACILITY_LINKER_GUIDE.md
- **How do I integrate with Kafka/ClickHouse?** See advanced integration guide in main documentation
- **How do I handle Amharic names?** Already built-in; see FacilityPreprocessor in main script

---

**Ready? Run:**

```bash
python demo_linker.py
```

**Expected time:** 2-4 minutes

Let me know if you have questions! 🎯
