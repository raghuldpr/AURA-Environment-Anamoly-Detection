"""AuraEngine: owns the data source, calibration, scoring, debounce and alerts.

Runs in its own thread so alerts keep working whether or not a dashboard is open.
The Streamlit app only reads snapshot() and calls the control methods.
"""
import csv
import threading
import time
from pathlib import Path

import numpy as np

from model import MIN_SAMPLES, AuraModel

UNCALIBRATED, CALIBRATING, NORMAL, ALERT = "uncalibrated", "calibrating", "normal", "alert"
CMD = {NORMAL: "0", ALERT: "1", CALIBRATING: "2", UNCALIBRATED: "2"}
FEATURES = ["Temperature (°C)", "Humidity (%)", "Light", "Gas"]


class AuraEngine:
    def __init__(self, source_factory, data_dir=Path(__file__).parent / "data", cal_seconds=240,
                 consecutive=3, contamination=0.20, max_points=300,
                 heartbeat=2.0, log=True, warmup_seconds=0):
        self.warmup_seconds = warmup_seconds   # MQ heater warm-up before calibrating
        self._first_data = None
        self.cal_seconds = cal_seconds
        self.consecutive = consecutive
        self.max_points = max_points
        self.heartbeat = heartbeat
        self.data_dir = Path(data_dir)
        self.log = log
        if log:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._rotate_old_log()

        self._lock = threading.RLock()
        self.model = AuraModel(contamination)
        self.state = UNCALIBRATED
        self.data = []             # dicts for charts
        self.cal = []              # calibration samples [t, h, l]
        self.cal_end = 0.0
        self.streak = 0
        self.score = None
        self.message = ""
        self.events = []           # [{ts, kind, text}], newest last
        self.alert_count = 0
        self._alert_started = None
        self._last_send = 0.0
        self._running = True

        self.reader = None         # on_connect may fire before this is assigned
        self.reader = source_factory(on_connect=self._send_state)
        threading.Thread(target=self._run, daemon=True).start()

    # ---------- controls (called from the UI) ----------
    def warmup_left(self):
        if self.warmup_seconds <= 0:
            return 0
        if self._first_data is None:
            return self.warmup_seconds
        return max(0, int(self._first_data + self.warmup_seconds - time.time()))

    def start_calibration(self):
        with self._lock:
            left = self.warmup_left()
            if left > 0:
                self.message = (f"Gas sensor warming up: wait {left} s before calibrating "
                                "(MQ readings drift while the heater warms).")
                return
            self.state = CALIBRATING
            self.cal = []
            self.cal_end = time.time() + self.cal_seconds
            self.streak = 0
            self.score = None
            self.message = ""
            self.model.model = None
            self._event("calibrating", f"Calibration started ({self.cal_seconds} s)")
        self._send_state()

    def _event(self, kind, text):
        """Append to the event log (lock held)."""
        self.events.append({"ts": time.time(), "kind": kind, "text": text})
        self.events = self.events[-100:]

    def _cause(self, x):
        """Describe which sensors deviate most from the baseline, e.g. 'Gas +4.1σ, Light −2.3σ'."""
        z = self.model.deviations(x)
        if z is None:
            return ""
        short = ["Temperature", "Humidity", "Light", "Gas"]
        top = sorted(zip(short, z), key=lambda p: -abs(p[1]))[:2]
        return ", ".join(f"{n} {v:+.1f}σ" for n, v in top if abs(v) >= 1.5)

    def reset(self):
        with self._lock:
            self.state = UNCALIBRATED
            self.model.model = None
            self.cal, self.streak, self.score, self.message = [], 0, None, ""
        self._send_state()

    def set_contamination(self, value):
        """Change sensitivity; refits on the stored calibration data if present."""
        with self._lock:
            self.model.contamination = value
            if self.state in (NORMAL, ALERT) and len(self.cal) >= MIN_SAMPLES:
                self.model.fit(self.cal)
                self.streak = 0

    def load_saved_calibration(self):
        path = self.data_dir / "calibration.csv"
        if not path.exists():
            with self._lock:
                self.message = "No saved calibration found."
            return False
        rows = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
        if rows.shape[1] != len(FEATURES):
            with self._lock:
                self.message = "Saved calibration is from an older sensor set. Recalibrate."
            return False
        with self._lock:
            self.cal = rows.tolist()
            self._finish_fit()
        return True

    def snapshot(self):
        with self._lock:
            return {
                "state": self.state,
                "data": list(self.data),
                "score": self.score,
                "n_cal": len(self.cal),
                "warmup_left": self.warmup_left(),
                "cal_left": max(0, int(self.cal_end - time.time())) if self.state == CALIBRATING else 0,
                "message": self.message,
                "connected": bool(self.reader.connected),
                "contamination": self.model.contamination,
                "events": list(self.events[-40:]),
                "alert_count": self.alert_count,
                "baseline": (None if self.model.mean_ is None else
                             {"mean": self.model.mean_.tolist(), "sigma": self.model.sigma_.tolist()}),
                "z": self._latest_z(),
            }

    def _latest_z(self):
        """Deviation (sigma units) of the latest reading from the baseline (lock held)."""
        if not self.data or self.state not in (NORMAL, ALERT):
            return None
        r = self.data[-1]
        return self.model.deviations([r[f] for f in FEATURES])

    def stop(self):
        self._running = False
        self.reader.stop()

    # ---------- internals ----------
    def _send_state(self):
        with self._lock:
            cmd = CMD[self.state]
        if self.reader is None:
            return
        self.reader.send(cmd)
        self._last_send = time.time()

    def _finish_fit(self):
        """Fit on self.cal (lock held). Sets state / message."""
        try:
            self.model.fit(self.cal)
        except ValueError as e:
            self.state = UNCALIBRATED
            self.message = f"Calibration failed: {e}. Check the sensor connection and try again."
            self._event("error", self.message)
            return
        self.state, self.streak, self.message = NORMAL, 0, ""
        self._event("calibrated", f"Calibration complete ({len(self.cal)} samples). Monitoring.")
        if self.log:
            with open(self.data_dir / "calibration.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["temp", "hum", "light", "gas"])
                w.writerows(self.cal)

    LOG_HEADER = ["timestamp", "temp", "hum", "light", "gas", "score", "state"]

    def _rotate_old_log(self):
        """If readings.csv has an older column layout, move it aside instead of mixing."""
        path = self.data_dir / "readings.csv"
        if path.exists():
            with open(path, newline="") as f:
                first = next(csv.reader(f), [])
            if first != self.LOG_HEADER:
                path.rename(self.data_dir / f"readings_old_{int(time.time())}.csv")

    def _log(self, ts, t, h, l, g, score, state):
        if not self.log:
            return
        path = self.data_dir / "readings.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "temp", "hum", "light", "gas", "score", "state"])
            w.writerow([f"{ts:.3f}", t, h, l, g, "" if score is None else f"{score:.4f}", state])

    def _process(self, ts, t, h, l, g):
        changed = False
        with self._lock:
            if self._first_data is None:
                self._first_data = time.time()
            row = {"time": ts, FEATURES[0]: t, FEATURES[1]: h, FEATURES[2]: l,
                   FEATURES[3]: g, "score": None, "anom": False}
            self.data.append(row)
            self.data = self.data[-self.max_points:]
            if self.state == CALIBRATING:
                self.cal.append([t, h, l, g])
                score = None
            elif self.state in (NORMAL, ALERT):
                score, anomaly = self.model.score([t, h, l, g])
                self.score = score
                row["score"], row["anom"] = score, bool(anomaly)
                self.streak = self.streak + 1 if anomaly else 0
                new_state = ALERT if self.streak >= self.consecutive else NORMAL
                if new_state != self.state:
                    self.state = new_state
                    changed = True
                    if new_state == ALERT:
                        self.alert_count += 1
                        self._alert_started = time.time()
                        cause = self._cause([t, h, l, g])
                        self._event("alert", "Anomaly detected" + (f": {cause}" if cause else ""))
                    else:
                        secs = int(time.time() - (self._alert_started or time.time()))
                        self._event("normal", f"Back to normal after {secs} s")
            else:
                score = None
            state = self.state
        self._log(ts, t, h, l, g, score if state != CALIBRATING else None, state)
        if state in (NORMAL, ALERT) and changed:
            self._send_state()

    def _run(self):
        while self._running:
            try:
                while not self.reader.q.empty():
                    self._process(*self.reader.q.get())
                with self._lock:
                    if self.state == CALIBRATING and time.time() >= self.cal_end:
                        self._finish_fit()
                        done = True
                    else:
                        done = False
                if done:
                    self._send_state()
                if time.time() - self._last_send >= self.heartbeat:
                    self._send_state()
            except Exception as e:  # keep the thread alive
                with self._lock:
                    self.message = f"Engine error: {e}"
            time.sleep(0.1)
