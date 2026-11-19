import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import ALERT, CALIBRATING, NORMAL, UNCALIBRATED, AuraEngine  # noqa: E402
from model import AuraModel  # noqa: E402
from simulator import SimulatedReader  # noqa: E402


def wait_for(cond, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def engine(tmp_path):
    e = AuraEngine(lambda on_connect: SimulatedReader(interval=0.02, on_connect=on_connect),
                   data_dir=tmp_path, cal_seconds=3, heartbeat=0.2)
    yield e
    e.stop()


def test_model_needs_min_samples():
    with pytest.raises(ValueError):
        AuraModel().fit([[1, 2, 3]] * 5)


def test_starts_uncalibrated_and_yellow(engine):
    assert engine.state == UNCALIBRATED
    assert wait_for(lambda: "2" in engine.reader.sent)


def test_calibrate_normal_then_alert_then_recover(engine):
    engine.start_calibration()
    assert engine.snapshot()["state"] == CALIBRATING
    assert wait_for(lambda: engine.state == NORMAL)
    assert wait_for(lambda: engine.reader.sent[-1] == "0")
    time.sleep(0.5)
    assert engine.state == NORMAL                  # no false alarm on normal data

    engine.reader.inject("combo")                  # dark AND hot
    assert wait_for(lambda: engine.state == ALERT)
    assert wait_for(lambda: engine.reader.sent[-1] == "1")

    engine.reader.inject(None)
    assert wait_for(lambda: engine.state == NORMAL)
    assert wait_for(lambda: engine.reader.sent[-1] == "0")


def test_gas_spike_alone_alerts(engine):
    engine.start_calibration()
    assert wait_for(lambda: engine.state == NORMAL)
    engine.reader.inject("gas")
    assert wait_for(lambda: engine.state == ALERT)


def test_warmup_blocks_calibration(tmp_path):
    e = AuraEngine(lambda on_connect: SimulatedReader(interval=0.02, on_connect=on_connect),
                   data_dir=tmp_path, cal_seconds=1, warmup_seconds=600)
    e.start_calibration()
    assert e.state == UNCALIBRATED and "warming up" in e.message
    e.stop()


def test_events_cause_and_baseline(engine):
    engine.start_calibration()
    assert wait_for(lambda: engine.state == NORMAL)
    s = engine.snapshot()
    assert s["baseline"] and len(s["baseline"]["mean"]) == 4
    assert any(e["kind"] == "calibrated" for e in s["events"])

    engine.reader.inject("gas")
    assert wait_for(lambda: engine.state == ALERT)
    s = engine.snapshot()
    assert s["alert_count"] == 1
    alert = [e for e in s["events"] if e["kind"] == "alert"][-1]
    assert "Gas" in alert["text"]                      # likely cause is named
    assert max(s["z"], key=abs) == s["z"][3]           # gas deviates most
    assert any(r["anom"] for r in s["data"])

    engine.reader.inject(None)
    assert wait_for(lambda: engine.state == NORMAL)
    assert any(e["kind"] == "normal" for e in engine.snapshot()["events"])


def test_single_blip_does_not_alert(engine):
    engine.start_calibration()
    assert wait_for(lambda: engine.state == NORMAL)
    engine.reader.inject("humid")
    time.sleep(0.03)                                # about one sample
    engine.reader.inject(None)
    time.sleep(0.5)
    assert engine.state == NORMAL


def test_failed_calibration_reports(tmp_path):
    e = AuraEngine(lambda on_connect: SimulatedReader(interval=5, on_connect=on_connect),
                   data_dir=tmp_path, cal_seconds=1)
    e.start_calibration()
    assert wait_for(lambda: e.state == UNCALIBRATED and "failed" in e.message)
    e.stop()


def test_heartbeat_resends_state(engine):
    n = len(engine.reader.sent)
    assert wait_for(lambda: len(engine.reader.sent) >= n + 3)
