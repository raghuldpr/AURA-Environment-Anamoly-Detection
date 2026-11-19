import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import AuraModel  # noqa: E402


def constant_th_calibration(n=120, seed=1):
    """DHT11-like: temperature and humidity constant, light and gas noisy."""
    rng = np.random.default_rng(seed)
    return np.c_[np.full(n, 29.2), np.full(n, 70.0),
                 1900 + rng.normal(0, 15, n), 108 + rng.normal(0, 4, n)]


def test_normal_points_are_normal():
    m = AuraModel()
    m.fit(constant_th_calibration())
    for x in ([29.2, 70, 1900, 108], [29.3, 70, 1910, 110], [29.1, 71, 1890, 105]):
        assert not m.score(x)[1]


def test_ambient_drift_does_not_alarm():
    """Regression: a normal room drifts ~20 % in light / ~10 % in gas; must stay normal."""
    m = AuraModel()
    m.fit(constant_th_calibration())
    assert not m.score([29.2, 70, 2250, 108])[1]    # light +350 (about +18 %)
    assert not m.score([29.2, 70, 1900, 120])[1]    # gas +12


def test_each_sensor_detected_even_if_constant_in_calibration():
    m = AuraModel()
    m.fit(constant_th_calibration())
    assert m.score([35.2, 70, 1900, 108])[1]      # temperature +6 C
    assert m.score([29.2, 90, 1900, 108])[1]      # humidity +20 %
    assert m.score([29.2, 70, 200, 108])[1]       # light covered
    assert m.score([29.2, 70, 1900, 2000])[1]     # gas spike
