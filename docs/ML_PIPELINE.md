# ML and feedback pipeline

ML estimates signal quality; it does not predict direction independently and
cannot override the rule engine.

Features are versioned through `ml/feature_schema.py`. Training applies
selection, imbalance handling, calibration, walk-forward validation and
recency weighting. Prediction confidence passes through `engine/ml_gate.py`,
which can veto or reduce confidence while preserving the rules decision.

Feedback is untrusted on receipt. The system compares candles, broker evidence,
trade duration, SL/TP traversal, duplicate payloads and statistical
consistency. Records move through pending, approved, rejected and gold
governance tiers. Dataset manifests are immutable, comparable and promotable.

Retraining requires minimum sample volume, multiple markets and strategies,
and sufficient quality. Candidate and active models are compared with win
rate, profit factor, expectancy, drawdown, precision, recall, F1 and Sharpe.
Promotion requires statistical improvement. Rollback activates a previous
registered version; datasets and models are never overwritten.

Production still requires external object storage so every API/worker instance
can load the same verified model artifact.
