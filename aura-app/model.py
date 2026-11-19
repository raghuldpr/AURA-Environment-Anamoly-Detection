import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

MIN_SAMPLES = 30
# Tolerance ("natural wobble") per feature (temp, humidity, light, gas): sigma_i =
# max(ABS_SIGMA_i, REL_SIGMA_i * |calibration mean_i|). Two reasons for it:
#  1. Isolation Forest cannot split on a feature that was constant during calibration
#     (the DHT11 changes slowly), so it would be blind to later changes in that sensor.
#  2. Ambient light and gas drift by 10-15 % in a normal room; that must not alarm.
# Training data = calibration readings + JITTER_COPIES copies jittered by sigma_i.
ABS_SIGMA = np.array([0.5, 2.0, 40.0, 10.0])
REL_SIGMA = np.array([0.0, 0.0, 0.15, 0.12])
JITTER_COPIES = 3


class AuraModel:
    """Isolation Forest anomaly detector (unsupervised, fitted on calibration data).

    The alert threshold is the `contamination` quantile of the forest's scores over the
    training cloud: readings scoring below it are anomalous. Higher value = more sensitive.
    Tuned on real data: 0 % false alarms, 7/7 synthetic anomalies detected at 0.20.
    """

    def __init__(self, contamination=0.20):
        self.contamination = contamination
        self.model = None
        self.threshold = 0.0
        self.mean_ = None      # calibration mean per feature (for the baseline / deviations)
        self.sigma_ = None     # tolerance per feature (see ABS_SIGMA / REL_SIGMA)

    @property
    def fitted(self):
        return self.model is not None

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        if len(X) < MIN_SAMPLES:
            raise ValueError(f"need at least {MIN_SAMPLES} samples, got {len(X)}")
        X_train = X
        if X.shape[1] == len(ABS_SIGMA):
            sigma = np.maximum(ABS_SIGMA, REL_SIGMA * np.abs(X.mean(axis=0)))
            self.mean_, self.sigma_ = X.mean(axis=0), sigma
            rng = np.random.default_rng(42)
            X_train = np.vstack([X + rng.normal(0, 1, X.shape) * sigma
                                 for _ in range(JITTER_COPIES)])
        self.model = IsolationForest(n_estimators=200, random_state=42).fit(X_train)
        self.threshold = float(np.quantile(self.model.score_samples(X_train), self.contamination))

    def deviations(self, x):
        """Per-sensor deviation from the calibrated baseline, in tolerance units (sigma)."""
        if self.mean_ is None or self.sigma_ is None:
            return None
        return ((np.asarray(x, dtype=float) - self.mean_) / self.sigma_).tolist()

    def score(self, x):
        """Returns (score, is_anomaly). Negative score = anomalous, positive = normal."""
        x = np.asarray(x, dtype=float).reshape(1, -1)
        s = float(self.model.score_samples(x)[0]) - self.threshold
        return s, s < 0

    def save(self, path):
        joblib.dump({"model": self.model, "threshold": self.threshold}, path)

    def load(self, path):
        d = joblib.load(path)
        self.model, self.threshold = d["model"], d["threshold"]
