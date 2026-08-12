"""
Two-Stage Facility Linking Pipeline: recordlinkage + LinkTransformer
=========================================================================
Stage 1: Fast blocking/candidate generation using recordlinkage
Stage 2: Semantic matching using LinkTransformer (Cross-Encoder)

Use for: Linking MFR, DHIS2, and eCHIS facility registries in NHDW
Author: Eyob Nebyou (Habtech)
Date: Week 2 NHDW Deliverable
"""

import pandas as pd
import numpy as np
import recordlinkage
from recordlinkage.preprocessing import clean
import re
from pathlib import Path
import logging
from typing import Tuple, Dict, List
import json
from datetime import datetime


def _json_safe(obj):
    """Convert numpy scalar types to native Python types for JSON serialization."""
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')

# For LinkTransformer semantic matching
from sentence_transformers import CrossEncoder
import torch

# Visualization and validation
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve, f1_score, confusion_matrix
import seaborn as sns

# ============================================================================
# CONFIGURATION
# ============================================================================

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('facility_linker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ethiopia health facility abbreviation expansions
HEALTH_FACILITY_EXPANSIONS = {
    'HC': 'Health Center',
    'HP': 'Health Post',
    'FMOH': 'Federal Ministry of Health',
    'RHB': 'Regional Health Bureau',
    'Hosp': 'Hospital',
    'Hosp.': 'Hospital',
    'Cli': 'Clinic',
    'Clinic': 'Clinic',
    'D/W': 'Delivery Ward',
    'PHC': 'Primary Health Center',
    'GH': 'General Hospital',
    'SH': 'Specialized Hospital',
    'Ref': 'Referral',
    'HEF': 'Health Extension Post',
    'Med': 'Medical',
    'Lab': 'Laboratory',
    'Disp': 'Dispensary',
}

# Amharic to English common facility name mappings
AMHARIC_ENGLISH_MAPPINGS = {
    'ሆስፒታል': 'Hospital',
    'ክሊኒክ': 'Clinic',
    'ጤና': 'Health',
    'መሀል': 'Central',
}

# Model configuration
MODEL_CONFIG = {
    'model_name': 'cross-encoder/ms-marco-MiniLM-L-12-v2',  # Fast, multilingual
    'max_length': 256,
    'batch_size': 64,
    'device': 'cuda' if torch.cuda.is_available() else 'cpu'
}

# Threshold calibration (to be overridden after manual validation)
DEFAULT_MATCH_THRESHOLD = 0.80

# ============================================================================
# SECTION 1: DATA PREPROCESSING
# ============================================================================

class FacilityPreprocessor:
    """Clean and normalize facility names and attributes."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @staticmethod
    def expand_abbreviations(text: str) -> str:
        """Expand common health facility abbreviations."""
        if pd.isna(text):
            return ""
        text = str(text)
        for abbr, full in HEALTH_FACILITY_EXPANSIONS.items():
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(abbr) + r'\b'
            text = re.sub(pattern, full, text, flags=re.IGNORECASE)
        return text
    
    @staticmethod
    def transliterate_amharic(text: str) -> str:
        """Handle Amharic script (basic mapping)."""
        if pd.isna(text):
            return ""
        text = str(text)
        for amharic, english in AMHARIC_ENGLISH_MAPPINGS.items():
            text = text.replace(amharic, english)
        return text
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Standard text normalization: lowercase, spacing, special chars."""
        if pd.isna(text):
            return ""
        text = str(text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Lowercase
        text = text.lower()
        # Remove common punctuation
        text = re.sub(r'[.,\-\/\(\):]', ' ', text)
        # Remove extra whitespace again after punctuation removal
        text = ' '.join(text.split())
        return text
    
    @staticmethod
    def phonetic_hash(text: str, method: str = 'soundex') -> str:
        """Generate phonetic hash for blocking (Soundex or Metaphone)."""
        if pd.isna(text) or not text:
            return ""
        from jellyfish import soundex, metaphone
        text = str(text).strip()
        if method == 'soundex':
            return soundex(text)[:4]  # First 4 chars of Soundex
        elif method == 'metaphone':
            return metaphone(text)[:4]
        return text[:4]
    
    def preprocess_facility_df(self, df: pd.DataFrame, 
                                name_col: str = 'facility_name',
                                preserve_cols: List[str] = None) -> pd.DataFrame:
        """
        Full preprocessing pipeline for a facility dataframe.
        
        Args:
            df: Input dataframe with facility records
            name_col: Name of the facility name column
            preserve_cols: List of columns to preserve (e.g., 'region', 'woreda')
        
        Returns:
            Preprocessed dataframe with new columns for linking
        """
        df = df.copy()
        
        # Facility name processing
        df[f'{name_col}_amharic_xlat'] = df[name_col].apply(self.transliterate_amharic)
        df[f'{name_col}_expanded'] = df[f'{name_col}_amharic_xlat'].apply(self.expand_abbreviations)
        df[f'{name_col}_normalized'] = df[f'{name_col}_expanded'].apply(self.normalize_text)
        df[f'{name_col}_phonetic'] = df[f'{name_col}_normalized'].apply(self.phonetic_hash)
        
        # Geographic normalization (if region/woreda/zone columns exist)
        for geo_col in ['region', 'zone', 'woreda']:
            if geo_col in df.columns:
                df[f'{geo_col}_normalized'] = df[geo_col].apply(
                    lambda x: self.normalize_text(str(x)) if pd.notna(x) else ""
                )
        
        self.logger.info(f"Preprocessed {len(df)} facility records")
        return df
    
    def save_preprocessed(self, df: pd.DataFrame, output_path: str):
        """Save preprocessed dataframe to CSV."""
        df.to_csv(output_path, index=False)
        self.logger.info(f"Saved preprocessed data to {output_path}")


# ============================================================================
# SECTION 2: STAGE 1 - RECORDLINKAGE BLOCKING
# ============================================================================

class RecordLinkageBlocker:
    """Stage 1: Fast candidate generation using recordlinkage."""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def block_facilities(self, df_a: pd.DataFrame, df_b: pd.DataFrame,
                        name_col: str = 'facility_name',
                        region_col: str = 'region',
                        phonetic_col: str = None) -> recordlinkage.Index:
        """
        Create candidate pairs using composite blocking strategy.
        
        Strategy:
        1. Soft regional blocking (allows cross-region if name is similar)
        2. Phonetic indexing on normalized facility names
        3. Fallback full index for edge cases
        
        Args:
            df_a: First dataframe (e.g., MFR)
            df_b: Second dataframe (e.g., DHIS2)
            name_col: Facility name column
            region_col: Region column for soft blocking
            phonetic_col: Phonetic hash column (if already computed)
        
        Returns:
            MultiIndex of candidate pairs (tuples of indices)
        """
        indexer = recordlinkage.Index()
        
        self.logger.info("Building multi-stage indexer...")
        
        phonetic_col_name = phonetic_col or f'{name_col}_phonetic'
        normalized_name_col = f'{name_col}_normalized'
        
        has_phonetic = phonetic_col_name in df_a.columns and phonetic_col_name in df_b.columns
        has_region = region_col in df_a.columns and region_col in df_b.columns
        has_normalized_name = normalized_name_col in df_a.columns and normalized_name_col in df_b.columns
        
        # Primary strategy: compound (AND) blocking — pairs must match on BOTH
        # region and phonetic code. This is far more restrictive than blocking
        # on each field independently and unioning the results, which is what
        # generated ~70k candidate pairs (barely better than a full cross join)
        # in the previous version.
        if has_phonetic and has_region:
            indexer.block([region_col, phonetic_col_name])
            self.logger.info(
                f"Added compound blocking on ({region_col}, {phonetic_col_name})"
            )
        elif has_phonetic:
            indexer.block(phonetic_col_name)
            self.logger.info(f"Added phonetic blocking on {phonetic_col_name}")
        elif has_region:
            indexer.block(region_col)
            self.logger.info(f"Added regional blocking on {region_col}")
        
        # Supplemental strategy: sorted neighbourhood on normalized name,
        # scoped within region via block_on, to catch near-misses (typos,
        # abbreviation differences) that an exact phonetic match would drop,
        # without reopening the full cross-region search space.
        if has_normalized_name and has_region:
            indexer.sortedneighbourhood(
                normalized_name_col, window=3, block_on=region_col
            )
            self.logger.info(
                f"Added region-scoped sorted neighbourhood indexing on {normalized_name_col}"
            )
        elif has_normalized_name:
            indexer.sortedneighbourhood(normalized_name_col, window=3)
            self.logger.info(f"Added sorted neighbourhood indexing on {normalized_name_col}")
        
        # Generate candidate pairs
        candidate_pairs = indexer.index(df_a, df_b)
        
        self.logger.info(f"Generated {len(candidate_pairs)} candidate pairs")
        return candidate_pairs
    
    def compute_blocking_features(self, df_a: pd.DataFrame, df_b: pd.DataFrame,
                                  candidate_pairs: recordlinkage.Index,
                                  name_col: str = 'facility_name') -> pd.DataFrame:
        """
        Compute traditional record linkage features for Stage 1 scoring.
        
        Features:
        - Levenshtein distance (name similarity)
        - Jaro-Winkler distance
        - Token/cosine similarity
        - Geographic proximity
        """
        from recordlinkage.compare import Exact, String
        
        self.logger.info("Computing Stage 1 blocking features...")
        
        compare = recordlinkage.Compare()
        
        # String comparison features
        compare.exact(f'{name_col}_normalized', f'{name_col}_normalized', 
                     label='name_exact')
        compare.string(f'{name_col}_normalized', f'{name_col}_normalized',
                      method='levenshtein', threshold=0.6, label='name_levenshtein')
        compare.string(f'{name_col}_normalized', f'{name_col}_normalized',
                      method='jaro_winkler', threshold=0.6, label='name_jaro_winkler')
        compare.string(f'{name_col}_normalized', f'{name_col}_normalized',
                      method='cosine', threshold=0.6, label='name_cosine')
        
        # Geographic comparisons
        if 'region' in df_a.columns and 'region' in df_b.columns:
            compare.exact('region_normalized' if 'region_normalized' in df_a.columns else 'region',
                         'region_normalized' if 'region_normalized' in df_b.columns else 'region',
                         label='region_exact')
        
        if 'woreda' in df_a.columns and 'woreda' in df_b.columns:
            compare.exact('woreda_normalized' if 'woreda_normalized' in df_a.columns else 'woreda',
                         'woreda_normalized' if 'woreda_normalized' in df_b.columns else 'woreda',
                         label='woreda_exact')
        
        # Compute features
        features = compare.compute(candidate_pairs, df_a, df_b)
        
        # Create feature summary
        features['feature_sum'] = features.sum(axis=1)
        features['feature_mean'] = features.mean(axis=1)
        
        self.logger.info(f"Computed features for {len(features)} candidate pairs")
        return features


# ============================================================================
# SECTION 3: STAGE 2 - LINKTRANSFORMER SEMANTIC MATCHING
# ============================================================================

class LinkTransformerMatcher:
    """Stage 2: Semantic matching using pretrained Cross-Encoder."""
    
    def __init__(self, model_name: str = None, device: str = None, logger=None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.model_name = model_name or MODEL_CONFIG['model_name']
        self.device = device or MODEL_CONFIG['device']
        
        self.logger.info(f"Loading model: {self.model_name}")
        self.model = CrossEncoder(self.model_name, max_length=MODEL_CONFIG['max_length'])
        self.model.to(self.device)
        self.logger.info(f"Model loaded on device: {self.device}")
    
    @staticmethod
    def create_pair_text(row_a: Dict, row_b: Dict, 
                        name_col: str = 'facility_name_normalized',
                        geo_cols: List[str] = None) -> str:
        """
        Combine facility record fields into a single comparison string.
        
        Designed for Cross-Encoder which expects two separate strings or 
        a concatenated context.
        """
        if geo_cols is None:
            geo_cols = ['woreda', 'region', 'zone']
        
        # Build text from both records with field labels
        parts_a = [row_a.get(name_col, '')]
        parts_b = [row_b.get(name_col, '')]
        
        for col in geo_cols:
            if col in row_a and pd.notna(row_a[col]):
                parts_a.append(f"{col}:{row_a[col]}")
            if col in row_b and pd.notna(row_b[col]):
                parts_b.append(f"{col}:{row_b[col]}")
        
        text_a = ' '.join(filter(None, parts_a))
        text_b = ' '.join(filter(None, parts_b))
        
        return text_a, text_b
    
    def score_candidate_pairs(self, df_a: pd.DataFrame, df_b: pd.DataFrame,
                             candidate_pairs: recordlinkage.Index,
                             name_col: str = 'facility_name_normalized',
                             batch_size: int = None,
                             show_progress: bool = True) -> pd.DataFrame:
        """
        Score all candidate pairs using the Cross-Encoder.
        
        Args:
            df_a: First dataframe (e.g., MFR)
            df_b: Second dataframe (e.g., DHIS2)
            candidate_pairs: RecordLinkage MultiIndex of pairs
            name_col: Facility name column to use
            batch_size: Batch size for inference
            show_progress: Show progress bar
        
        Returns:
            DataFrame with columns: mfr_id, dhis2_id, score, text_a, text_b
        """
        batch_size = batch_size or MODEL_CONFIG['batch_size']
        
        self.logger.info(f"Scoring {len(candidate_pairs)} candidate pairs...")
        
        # Convert dataframes to record dicts for fast lookup
        mfr_records = df_a.to_dict('index')
        dhis2_records = df_b.to_dict('index')
        
        # Prepare pair texts for batch inference
        pair_texts = []
        pair_indices = []
        
        for mfr_idx, dhis2_idx in candidate_pairs:
            mfr_rec = mfr_records[mfr_idx]
            dhis2_rec = dhis2_records[dhis2_idx]
            
            text_a, text_b = self.create_pair_text(mfr_rec, dhis2_rec, name_col)
            pair_texts.append([text_a, text_b])
            pair_indices.append((mfr_idx, dhis2_idx))
        
        # Score in batches
        scores = []
        for i in range(0, len(pair_texts), batch_size):
            batch = pair_texts[i:i + batch_size]
            batch_scores = self.model.predict(batch, convert_to_numpy=True)
            scores.extend(batch_scores)
            
            if show_progress and (i + batch_size) % (batch_size * 10) == 0:
                self.logger.info(f"Scored {min(i + batch_size, len(pair_texts))} pairs")
        
        # Normalize scores to 0-1 range
        scores = np.array(scores)
        scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
        
        # Create results dataframe
        results = []
        for (mfr_idx, dhis2_idx), score, (text_a, text_b) in zip(
            pair_indices, scores, pair_texts
        ):
            mfr_rec = mfr_records[mfr_idx]
            dhis2_rec = dhis2_records[dhis2_idx]
            
            results.append({
                'mfr_id': mfr_rec.get('facility_id', mfr_idx),
                'mfr_name': mfr_rec.get('facility_name_normalized', ''),
                'mfr_region': mfr_rec.get('region', ''),
                'dhis2_id': dhis2_rec.get('facility_id', dhis2_idx),
                'dhis2_name': dhis2_rec.get('facility_name_normalized', ''),
                'dhis2_region': dhis2_rec.get('region', ''),
                'linktransformer_score': float(score),
                'text_a': text_a,
                'text_b': text_b
            })
        
        results_df = pd.DataFrame(results)
        self.logger.info(f"Scoring complete. Mean score: {results_df['linktransformer_score'].mean():.3f}")
        
        return results_df


# ============================================================================
# SECTION 4: THRESHOLD CALIBRATION & VALIDATION
# ============================================================================

class ThresholdCalibrator:
    """Calibrate optimal match threshold using manual validation data."""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    @staticmethod
    def compute_metrics(true_labels, scores, threshold):
        """Compute precision, recall, F1 for a given threshold."""
        predicted = (scores >= threshold).astype(int)
        
        tp = ((predicted == 1) & (true_labels == 1)).sum()
        fp = ((predicted == 1) & (true_labels == 0)).sum()
        fn = ((predicted == 0) & (true_labels == 1)).sum()
        tn = ((predicted == 0) & (true_labels == 0)).sum()
        
        precision = tp / (tp + fp + 1e-10)
        recall = tp / (tp + fn + 1e-10)
        f1 = 2 * (precision * recall) / (precision + recall + 1e-10)
        
        return {
            'threshold': threshold,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp,
            'fn': fn,
            'tn': tn
        }
    
    def calibrate_threshold(self, scores: np.ndarray, true_labels: np.ndarray,
                           output_path: str = 'threshold_calibration.json') -> Tuple[float, Dict]:
        """
        Find optimal threshold using F1 score.
        
        Args:
            scores: Array of similarity scores
            true_labels: Array of true labels (0/1)
            output_path: Path to save calibration results
        
        Returns:
            Tuple of (optimal_threshold, metrics_dict)
        """
        self.logger.info("Calibrating threshold using manual validation data...")
        
        thresholds = np.arange(0.5, 1.0, 0.01)
        results = []
        
        for threshold in thresholds:
            metrics = self.compute_metrics(true_labels, scores, threshold)
            results.append(metrics)
        
        results_df = pd.DataFrame(results)
        optimal_idx = results_df['f1'].idxmax()
        optimal_result = results_df.iloc[optimal_idx].to_dict()
        
        self.logger.info(
            f"Optimal threshold: {optimal_result['threshold']:.3f} "
            f"(F1: {optimal_result['f1']:.3f}, Precision: {optimal_result['precision']:.3f}, "
            f"Recall: {optimal_result['recall']:.3f})"
        )
        
        # Save results
        with open(output_path, 'w') as f:
            json.dump({
                'optimal_threshold': float(optimal_result['threshold']),
                'all_results': results
            }, f, indent=2, default=_json_safe)
        
        # Plot precision-recall curve
        plt.figure(figsize=(10, 6))
        plt.plot(results_df['recall'], results_df['precision'], marker='o', label='Precision-Recall Curve')
        plt.axvline(x=optimal_result['recall'], color='r', linestyle='--', label=f"Optimal @ {optimal_result['threshold']:.3f}")
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('Precision-Recall Curve: LinkTransformer Threshold Calibration')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('precision_recall_curve.png', dpi=300, bbox_inches='tight')
        self.logger.info("Saved precision-recall curve to precision_recall_curve.png")
        
        return float(optimal_result['threshold']), optimal_result
    
    def plot_confusion_matrix(self, scores: np.ndarray, true_labels: np.ndarray,
                             threshold: float, output_path: str = 'confusion_matrix.png'):
        """Visualize confusion matrix at optimal threshold."""
        predicted = (scores >= threshold).astype(int)
        cm = confusion_matrix(true_labels, predicted)
        
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False)
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        plt.title(f'Confusion Matrix @ Threshold {threshold:.3f}')
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        self.logger.info(f"Saved confusion matrix to {output_path}")


# ============================================================================
# SECTION 5: END-TO-END PIPELINE
# ============================================================================

class FacilityLinkingPipeline:
    """Orchestrate the complete two-stage linking pipeline."""
    
    def __init__(self, output_dir: str = './facility_linking_output'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"Pipeline output directory: {self.output_dir}")
        
        self.preprocessor = FacilityPreprocessor()
        self.blocker = RecordLinkageBlocker(logger=self.logger)
        self.linker = LinkTransformerMatcher(logger=self.logger)
        self.calibrator = ThresholdCalibrator(logger=self.logger)
    
    def run(self, mfr_df: pd.DataFrame, dhis2_df: pd.DataFrame,
            manual_validation_df: pd.DataFrame = None,
            match_threshold: float = None,
            save_intermediate: bool = True) -> Dict:
        """
        Execute the complete pipeline.
        
        Args:
            mfr_df: MFR facilities dataframe
            dhis2_df: DHIS2 facilities dataframe
            manual_validation_df: Manual validation labels (optional, for calibration)
            match_threshold: Override threshold (if None, uses default or calibrates)
            save_intermediate: Save intermediate results
        
        Returns:
            Dictionary with results, metrics, and file paths
        """
        self.logger.info("=" * 80)
        self.logger.info("STARTING TWO-STAGE FACILITY LINKING PIPELINE")
        self.logger.info("=" * 80)
        
        results = {'timestamp': datetime.now().isoformat()}
        
        # -------- PREPROCESSING --------
        self.logger.info("\n--- STAGE 0: PREPROCESSING ---")
        mfr_preprocessed = self.preprocessor.preprocess_facility_df(mfr_df)
        dhis2_preprocessed = self.preprocessor.preprocess_facility_df(dhis2_df)
        
        if save_intermediate:
            mfr_preprocessed.to_csv(
                self.output_dir / 'mfr_preprocessed.csv', index=False
            )
            dhis2_preprocessed.to_csv(
                self.output_dir / 'dhis2_preprocessed.csv', index=False
            )
            self.logger.info("Saved preprocessed dataframes")
        
        results['mfr_count'] = len(mfr_preprocessed)
        results['dhis2_count'] = len(dhis2_preprocessed)
        
        # -------- STAGE 1: BLOCKING --------
        self.logger.info("\n--- STAGE 1: RECORDLINKAGE BLOCKING ---")
        candidate_pairs = self.blocker.block_facilities(
            mfr_preprocessed, dhis2_preprocessed
        )
        results['candidate_pairs_count'] = len(candidate_pairs)
        
        # Compute blocking features
        blocking_features = self.blocker.compute_blocking_features(
            mfr_preprocessed, dhis2_preprocessed, candidate_pairs
        )
        
        self.logger.info(f"Blocking reduced candidate space: "
                        f"{len(mfr_preprocessed) * len(dhis2_preprocessed):,} → "
                        f"{len(candidate_pairs):,} pairs "
                        f"({100 * len(candidate_pairs) / (len(mfr_preprocessed) * len(dhis2_preprocessed)):.2f}%)")
        
        if save_intermediate:
            blocking_features.to_csv(
                self.output_dir / 'stage1_blocking_features.csv'
            )
        
        # -------- STAGE 2: LINKTRANSFORMER --------
        self.logger.info("\n--- STAGE 2: LINKTRANSFORMER SEMANTIC MATCHING ---")
        scored_pairs = self.linker.score_candidate_pairs(
            mfr_preprocessed, dhis2_preprocessed, candidate_pairs
        )
        
        if save_intermediate:
            scored_pairs.to_csv(
                self.output_dir / 'stage2_linktransformer_scores.csv', index=False
            )
        
        results['scored_pairs_count'] = len(scored_pairs)
        results['linktransformer_score_stats'] = {
            'mean': float(scored_pairs['linktransformer_score'].mean()),
            'median': float(scored_pairs['linktransformer_score'].median()),
            'min': float(scored_pairs['linktransformer_score'].min()),
            'max': float(scored_pairs['linktransformer_score'].max()),
            'std': float(scored_pairs['linktransformer_score'].std())
        }
        
        # -------- THRESHOLD CALIBRATION --------
        self.logger.info("\n--- THRESHOLD CALIBRATION ---")
        
        if manual_validation_df is not None and len(manual_validation_df) > 0:
            self.logger.info(f"Using {len(manual_validation_df)} manual validation labels")
            
            # Merge scores with labels
            merged = scored_pairs.merge(
                manual_validation_df[['mfr_id', 'dhis2_id', 'label']],
                on=['mfr_id', 'dhis2_id'],
                how='inner'
            )
            
            if len(merged) > 0:
                optimal_threshold, calibration_metrics = self.calibrator.calibrate_threshold(
                    merged['linktransformer_score'].values,
                    merged['label'].values,
                    output_path=str(self.output_dir / 'threshold_calibration.json')
                )
                self.calibrator.plot_confusion_matrix(
                    merged['linktransformer_score'].values,
                    merged['label'].values,
                    optimal_threshold,
                    output_path=str(self.output_dir / 'confusion_matrix.png')
                )
                results['calibration'] = calibration_metrics
            else:
                self.logger.warning("No matching records between scores and validation labels")
                optimal_threshold = match_threshold or DEFAULT_MATCH_THRESHOLD
        else:
            self.logger.info("No manual validation data provided; using default threshold")
            optimal_threshold = match_threshold or DEFAULT_MATCH_THRESHOLD
        
        results['match_threshold'] = optimal_threshold
        
        # -------- FINAL MATCHING --------
        self.logger.info("\n--- FINAL MATCHING ---")
        final_matches = scored_pairs[scored_pairs['linktransformer_score'] >= optimal_threshold].copy()
        final_matches['match_type'] = 'confirmed'
        
        self.logger.info(f"Final matches at threshold {optimal_threshold:.3f}: {len(final_matches)}")
        
        # Calculate coverage
        mfr_matched = final_matches['mfr_id'].nunique()
        dhis2_matched = final_matches['dhis2_id'].nunique()
        
        results['final_matches'] = {
            'total': len(final_matches),
            'mfr_matched': mfr_matched,
            'dhis2_matched': dhis2_matched,
            'mfr_coverage': f"{100 * mfr_matched / len(mfr_preprocessed):.1f}%",
            'dhis2_coverage': f"{100 * dhis2_matched / len(dhis2_preprocessed):.1f}%"
        }
        
        # Save final matches
        final_matches.to_csv(
            self.output_dir / 'final_facility_matches.csv', index=False
        )
        self.logger.info(f"Saved final matches to final_facility_matches.csv")
        
        # -------- SUMMARY REPORT --------
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PIPELINE SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"MFR Records: {results['mfr_count']:,}")
        self.logger.info(f"DHIS2 Records: {results['dhis2_count']:,}")
        self.logger.info(f"Candidate Pairs (Stage 1): {results['candidate_pairs_count']:,}")
        self.logger.info(f"Match Threshold: {optimal_threshold:.3f}")
        self.logger.info(f"Final Matches: {results['final_matches']['total']:,}")
        self.logger.info(f"MFR Coverage: {results['final_matches']['mfr_coverage']}")
        self.logger.info(f"DHIS2 Coverage: {results['final_matches']['dhis2_coverage']}")
        
        # Save summary report
        with open(self.output_dir / 'pipeline_summary.json', 'w') as f:
            json.dump(results, f, indent=2, default=_json_safe)
        
        return results


# ============================================================================
# SECTION 6: EXAMPLE USAGE
# ============================================================================

def create_sample_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create sample MFR, DHIS2, and validation data for testing."""
    
    # Sample MFR data
    mfr_data = {
        'facility_id': ['MFR_001', 'MFR_002', 'MFR_003', 'MFR_004', 'MFR_005'],
        'facility_name': [
            'Addis Ababa HC', 'Hawassa Referral Hosp', 'Dire Dawa Clinic',
            'Bole Health Center', 'Adama Hospital'
        ],
        'region': ['Addis Ababa', 'SNNPR', 'Dire Dawa', 'Addis Ababa', 'Oromia'],
        'woreda': ['Bole', 'Hawassa', 'Dire Dawa', 'Bole', 'Adama'],
        'zone': ['Central', 'Zone1', 'Zone1', 'Central', 'East'],
        'phone': ['0111234567', '0912345678', '0911234567', '0111111111', '0922222222']
    }
    
    # Sample DHIS2 data (some are duplicates, some different)
    dhis2_data = {
        'facility_id': ['DHIS2_001', 'DHIS2_002', 'DHIS2_003', 'DHIS2_004', 'DHIS2_005'],
        'facility_name': [
            'Addis Ababa Health Center', 'Hawasa General Hospital', 'Dire Dawa Dispensary',
            'Bole HC', 'Adama Gen Hosp'
        ],
        'region': ['Addis Ababa', 'SNNPR', 'Dire Dawa', 'Addis Ababa', 'Oromia'],
        'woreda': ['Bole', 'Hawassa', 'Dire Dawa', 'Bole', 'Adama'],
        'zone': ['Central', 'Zone1', 'Zone1', 'Central', 'East'],
        'phone': ['0111234567', '0912345678', '0911234567', None, '0922222222']
    }
    
    # Sample manual validation (for threshold calibration)
    validation_data = {
        'mfr_id': ['MFR_001', 'MFR_002', 'MFR_003', 'MFR_004', 'MFR_005'],
        'dhis2_id': ['DHIS2_001', 'DHIS2_002', 'DHIS2_003', 'DHIS2_004', 'DHIS2_005'],
        'label': [1, 1, 1, 1, 1]  # All are correct matches in this toy example
    }
    
    return (
        pd.DataFrame(mfr_data),
        pd.DataFrame(dhis2_data),
        pd.DataFrame(validation_data)
    )


if __name__ == "__main__":
    # -------- EXAMPLE USAGE --------
    
    # Option 1: Load your own data
    # mfr_df = pd.read_csv('path/to/mfr.csv')
    # dhis2_df = pd.read_csv('path/to/dhis2.csv')
    # validation_df = pd.read_csv('path/to/manual_validation.csv')
    
    # Option 2: Use sample data
    mfr_df, dhis2_df, validation_df = create_sample_data()
    
    # Initialize and run pipeline
    pipeline = FacilityLinkingPipeline(output_dir='./facility_linking_output')
    
    results = pipeline.run(
        mfr_df=mfr_df,
        dhis2_df=dhis2_df,
        manual_validation_df=validation_df,
        save_intermediate=True
    )
    
    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print(f"\nResults saved to: ./facility_linking_output/")
    print(f"\nKey metrics:")
    print(f"  - Final matches: {results['final_matches']['total']}")
    print(f"  - MFR coverage: {results['final_matches']['mfr_coverage']}")
    print(f"  - DHIS2 coverage: {results['final_matches']['dhis2_coverage']}")
    print(f"  - Match threshold: {results['match_threshold']:.3f}")
