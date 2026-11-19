"""Fake ESP32 for testing without hardware. Same interface as SerialReader."""
import queue
import random
import threading
import time


class SimulatedReader:
    """Generates warm+bright / cool+dim correlated 'normal' data.
    Call inject(kind) to create anomalies: 'dark', 'humid', 'hot', 'gas', 'combo'."""

    def __init__(self, interval=0.2, on_connect=None):
        self.interval = interval
        self.q = queue.Queue()
        self.connected = True
        self.running = True
        self.sent = []                 # commands received (for tests)
        self.anomaly = None
        self._phase = 0.0
        if on_connect:
            on_connect()
        threading.Thread(target=self._run, daemon=True).start()

    def inject(self, kind):
        self.anomaly = kind

    def _sample(self):
        self._phase += 0.3   # one full light/temperature cycle every ~21 samples
        sweep = (1 + __import__("math").sin(self._phase)) / 2    # 0..1
        t = 24 + 4 * sweep + random.gauss(0, 0.15)
        h = 55 - 8 * sweep + random.gauss(0, 0.5)
        l = 600 + 1400 * sweep + random.gauss(0, 25)
        g = 350 + 60 * sweep + random.gauss(0, 8)
        if self.anomaly == "gas":
            g += 700
        if self.anomaly in ("dark", "combo"):
            l = 40 + random.gauss(0, 5)
        if self.anomaly in ("hot", "combo"):
            t += 8
        if self.anomaly == "humid":
            h += 25
        return t, h, l, g

    def _run(self):
        while self.running:
            self.q.put((time.time(), *self._sample()))
            time.sleep(self.interval)

    def send(self, cmd):
        self.sent.append(cmd)

    def stop(self):
        self.running = False
