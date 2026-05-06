"""
Risk-prediction ML pipeline.

Modules:
  - features  : extract a feature vector from a project's flow (Gherkin + DOM + history)
  - dataset   : synthesise a labelled training CSV
  - train     : fit a RandomForest, persist model + metrics to data/
  - predict   : load the model and score a feature vector
"""

from app.ml.features import FLOW_BUCKETS, FEATURE_COLUMNS, FlowFeatures, bucket_for_label

__all__ = ["FLOW_BUCKETS", "FEATURE_COLUMNS", "FlowFeatures", "bucket_for_label"]
