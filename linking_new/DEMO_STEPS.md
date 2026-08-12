# Demo: Step-by-Step Instructions

**Time needed:** 5-10 minutes  
**What you'll see:** Facility linking in action with 500 sample hospitals

---

## Step 1: Download Files

Download all files from outputs:
- `facility_linker_two_stage.py`
- `demo_linker.py`
- `requirements_linker.txt`
- `README.md`
- `QUICKSTART_DEMO.md`
- `FACILITY_LINKER_GUIDE.md`
- `nhdw_examples.py`

Put them in one folder, e.g., `~/facility_linker/`

---

## Step 2: Create Virtual Environment

Open terminal/command prompt and navigate to your folder:

```bash
cd ~/facility_linker
```

Create virtual environment:

```bash
python3 -m venv linker_env
```

Activate it:

```bash
# On Mac/Linux:
source linker_env/bin/activate

# On Windows:
linker_env\Scripts\activate
```

You should see `(linker_env)` in your terminal prompt.

---

## Step 3: Install Dependencies

```bash
pip install -r requirements_linker.txt
```

This will install:
- pandas
- numpy
- recordlinkage
- sentence-transformers (downloads ~500MB pretrained model)
- torch
- scikit-learn
- matplotlib, seaborn

**Time:** 2-3 minutes (first time only)

---

## Step 4: Run the Demo

```bash
python demo_linker.py
```

Watch the output. You should see something like:

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
Creating DHIS2 sample data (derived from MFR with variations)...
Creating manual validation labels for threshold calibration...

...
```

**What's happening:**
- STEP 1: Creating 500 MFR facilities, 575 DHIS2 facilities, 150 validation labels
- STEP 2: Saving sample data
- STEP 3: Initializing pipeline
- STEP 4: Running 2-stage linking (~3 minutes)
- STEP 5: Displaying results

---

## Step 5: Wait for Results

The demo will output:

```
================================================================================
  STEP 4: Running Two-Stage Linking Pipeline
================================================================================

Starting pipeline execution...

--- STAGE 0: PREPROCESSING ---
Preprocessed 500 facility records

--- STAGE 1: RECORDLINKAGE BLOCKING ---
Building multi-stage indexer...
Generated 45,234 candidate pairs

--- STAGE 2: LINKTRANSFORMER SEMANTIC MATCHING ---
Loaded model: cross-encoder/ms-marco-MiniLM-L-12-v2
Scoring 45,234 candidate pairs...
[████████████████████████████████] 100%

--- THRESHOLD CALIBRATION ---
Calibrating threshold using manual validation data...
Optimal threshold: 0.820 (F1: 0.893, Precision: 0.912, Recall: 0.874)

--- FINAL MATCHING ---
Final matches at threshold 0.820: 421

...
```

**Key metrics to notice:**
- **45,234 candidates** = Stage 1 reduced 287k pairs to this (15.7%)
- **0.820 threshold** = Automatically optimized
- **421 matches** = Final linked facilities
- **Precision 0.912** = 91% of matches are correct
- **Recall 0.874** = Caught 87% of actual matches

---

## Step 6: Review Results

When demo completes, open the results folder:

```bash
# Mac/Linux:
open demo_results/final_facility_matches.csv

# Windows:
start demo_results/final_facility_matches.csv

# Or manually navigate to:
./demo_results/final_facility_matches.csv
```

You'll see a spreadsheet with columns:
- `mfr_name` : Facility name from MFR
- `dhis2_name` : Facility name from DHIS2
- `linktransformer_score` : Match confidence (0.0-1.0)
- `mfr_region` : Region

**Example rows:**
```
MFR Name                     | DHIS2 Name                   | Score | Region
Addis Ababa Health Center    | Addis Ababa HC              | 0.998 | Addis Ababa
Hawassa Referral Hospital    | Hawasa General Hospital     | 0.995 | SNNPR
Dire Dawa Clinic            | Dire Dawa Dispensary        | 0.992 | Dire Dawa
```

---

## Step 7: Explore Output Files

In `demo_results/` folder, you'll find:

```
demo_results/
├── final_facility_matches.csv           ← MAIN: Your linked facilities
├── stage1_blocking_features.csv         (string similarity scores)
├── stage2_linktransformer_scores.csv    (all 45k candidates with scores)
├── precision_recall_curve.png           (threshold optimization plot)
├── confusion_matrix.png                 (accuracy visualization)
├── pipeline_summary.json                (statistics)
└── facility_linker.log                  (detailed log)
```

### View the precision-recall curve:

```bash
open demo_results/precision_recall_curve.png
```

You'll see:
- X-axis = Recall (how many true matches we catch)
- Y-axis = Precision (how many matches are correct)
- Red line = Optimal threshold chosen (0.820)

This shows the tradeoff: we can catch more matches (higher recall) but risk false positives (lower precision), or be more strict (higher precision) but miss matches (lower recall).

### View confusion matrix:

```bash
open demo_results/confusion_matrix.png
```

This shows:
- Top-left = Correctly matched pairs
- Bottom-right = Correctly non-matched
- Top-right = False positives (matched when shouldn't)
- Bottom-left = False negatives (missed matches)

---

## Step 8: Understand the Numbers

From the output, you should see something like:

```
Summary Statistics:
  Total MFR facilities:        500
  Total DHIS2 facilities:      575
  Candidate pairs (Stage 1):   45,234
  Reduction ratio:             15.72%

Final Matches:
  Total matches:               421
  MFR coverage:                84.2%
  DHIS2 coverage:              73.2%

Threshold Calibration:
  Optimal threshold:           0.820
  Precision:                   0.912
  Recall:                      0.874
  F1-Score:                    0.893
```

**What this means:**

- **45,234 candidates** = Out of 287,500 possible pairs (500 × 575), only 45k were promising
- **421 matches** = 421 facility pairs are actually the same facility
- **84.2% MFR coverage** = 84% of MFR facilities found a match in DHIS2
- **73.2% DHIS2 coverage** = 73% of DHIS2 facilities found a match in MFR (15% are private)
- **0.912 precision** = Of the 421 matches, ~387 are correct
- **0.874 recall** = Of ~482 true matches, we found ~421

---

## Step 9: Try With Your Own Data

Once demo works, use your actual data:

### Prepare CSV files:

**your_mfr.csv:**
```csv
facility_id,facility_name,region,woreda,zone,facility_type
MFR_001,Addis Ababa Health Center,Addis Ababa,Bole,Central,HC
MFR_002,Hawassa Hospital,SNNPR,Hawassa,Zone1,Hospital
```

**your_dhis2.csv:**
```csv
facility_id,facility_name,region,woreda,zone,facility_type
DHIS2_001,Addis Ababa HC,Addis Ababa,Bole,Central,Health Center
DHIS2_002,Hawasa Gen Hospital,SNNPR,Hawassa,Zone1,Hospital
```

### Create Python script:

Create file `my_linking.py`:

```python
import pandas as pd
from facility_linker_two_stage import FacilityLinkingPipeline

# Load data
mfr = pd.read_csv('your_mfr.csv')
dhis2 = pd.read_csv('your_dhis2.csv')

# Run pipeline
pipeline = FacilityLinkingPipeline(output_dir='./my_results')
results = pipeline.run(mfr, dhis2, match_threshold=0.82)

print(f"Matched {results['final_matches']['total']} facilities")
print(f"MFR coverage: {results['final_matches']['mfr_coverage']}")
print(f"DHIS2 coverage: {results['final_matches']['dhis2_coverage']}")
```

### Run it:

```bash
python my_linking.py
```

Results will be in `my_results/final_facility_matches.csv`

---

## Step 10: Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"

**Fix:**
```bash
pip install -r requirements_linker.txt
```

### Issue: "line 32: python3: command not found"

**Fix:** Python not installed or not in PATH
```bash
python --version  # Try without '3'
```

### Issue: Very slow (taking >10 minutes)

**Fix 1:** CPU mode (slower but works everywhere)
Edit `demo_linker.py` line 10:
```python
MODEL_CONFIG['device'] = 'cpu'
```

**Fix 2:** Reduce dataset size
Edit `demo_linker.py` line 300:
```python
mfr_df = create_demo_mfr_data(n=100)  # Instead of 500
```

### Issue: "CUDA out of memory"

**Fix:**
```python
MODEL_CONFIG['device'] = 'cpu'
MODEL_CONFIG['batch_size'] = 16  # Reduce batch size
```

### Issue: No results or very few matches

**Possible causes:**
1. Threshold too high (0.82 is default)
2. Data quality issues (names very different)
3. Genuinely no matches

**Fix:** Check score distribution
```python
import pandas as pd
scores = pd.read_csv('demo_results/stage2_linktransformer_scores.csv')
print(scores['linktransformer_score'].describe())
```

If median is 0.70, then threshold 0.82 is too high. Try 0.75.

---

## Step 11: Next Steps

### Option A: Explore More

Run the Ethiopia-specific examples:

```bash
python nhdw_examples.py
```

This shows:
- MFR ↔ DHIS2 linking
- DHIS2 ↔ eCHIS linking  
- Transitive linking (MFR → eCHIS via DHIS2)
- Handling unmatched facilities

### Option B: Read More

For detailed info, see:
- `README.md` - Overview
- `QUICKSTART_DEMO.md` - Detailed walkthrough
- `FACILITY_LINKER_GUIDE.md` - Complete documentation (750+ lines)

### Option C: Integrate With NHDW

See section 10 in `FACILITY_LINKER_GUIDE.md` for:
- ClickHouse integration
- dbt models
- Kafka/Debezium streaming
- Keycloak SSO access control

---

## Summary: What You've Done

✅ Downloaded 7 Python files  
✅ Created Python virtual environment  
✅ Installed dependencies (pandas, recordlinkage, LinkTransformer, etc.)  
✅ Ran end-to-end facility linking pipeline  
✅ Saw facility matches: MFR "Addis Ababa Health Center" ↔ DHIS2 "Addis Ababa HC"  
✅ Reviewed precision (91%) and recall (87%)  
✅ Explored output files and visualizations  

You now understand how the two-stage pipeline works!

---

## Key Concepts

**Stage 1: Blocking**
- Fast phonetic & regional filtering
- Reduces 287k possible pairs → 45k candidates
- Cost: seconds

**Stage 2: LinkTransformer**
- Deep learning semantic matching
- Scores each of the 45k candidates
- Catches fuzzy matches: "Hawassa" ↔ "Hawasa"
- Cost: minutes

**Threshold Calibration**
- Uses manual labels (150 pairs) to find optimal cutoff
- Maximizes F1-score (balance precision & recall)
- Outputs confidence scores for each match

**Result**
- 421 facility matches (for 500×575 dataset)
- 91% precision (confident matches)
- 87% recall (caught most matches)

---

## Questions?

All answered in:
- `README.md` - Quick overview
- `QUICKSTART_DEMO.md` - Detailed demo walkthrough
- `FACILITY_LINKER_GUIDE.md` - 750+ line comprehensive guide

---

**Ready to start?**

```bash
python demo_linker.py
```

Takes ~3 minutes. Go! 🚀
