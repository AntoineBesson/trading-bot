from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
import pandas as pd
import numpy as np

class MetaLabeler:
    """
    The Meta-Labeler is a Secondary Model.
    It takes the output of the Primary Model (Side) and other features (Volatility, etc.)
    and predicts whether the Primary Model's signal will result in a profit.
    
    Target Variable (y): 1 if trade profitable, 0 otherwise.
    Features (X): Volatility, serial correlation, maybe the primary signal itself, etc.
    """
    
    def __init__(self, n_estimators=100, max_depth=5, min_samples_leaf=10, random_state=42):
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth, 
            min_samples_leaf=min_samples_leaf,
            class_weight='balanced_subsample', # Important for imbalanced datasets
            random_state=random_state,
            n_jobs=-1
        )
        
    def fit(self, X: pd.DataFrame, y: pd.Series):
        """
        Trains the Random Forest model.
        """
        # Ensure alignment
        common_idx = X.index.intersection(y.index)
        X_aligned = X.loc[common_idx]
        y_aligned = y.loc[common_idx]
        
        print(f"Training Meta-Labeler on {len(X_aligned)} samples...")
        self.model.fit(X_aligned, y_aligned)
        
    def predict(self, X: pd.DataFrame) -> pd.Series:
        """
        Returns the probability of Class 1 (Trade Success).
        """
        # 1. Get probabilities
        proba = self.model.predict_proba(X)
        
        # Depending on classes order, getting index for class 1
        # classes_ usually [0, 1]
        pos_idx = np.where(self.model.classes_ == 1)[0][0]
        
        return pd.Series(proba[:, pos_idx], index=X.index, name='prob_success')
        
    def evaluate(self, X, y):
        """
        Prints evaluation metrics.
        """
        common_idx = X.index.intersection(y.index)
        X = X.loc[common_idx]
        y = y.loc[common_idx]
        
        preds = self.model.predict(X)
        probs = self.predict(X)
        
        print("\n--- Meta-Labeler Evaluation ---")
        print(classification_report(y, preds))
        print("Confusion Matrix:")
        print(confusion_matrix(y, preds))
        
        try:
            auc = roc_auc_score(y, probs)
            print(f"ROC AUC: {auc:.4f}")
        except Exception:
            print("ROC AUC: N/A (One class only?)")
            
        return preds
