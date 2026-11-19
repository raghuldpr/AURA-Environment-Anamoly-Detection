"""Serial source: reads 'temp,hum,light,gas' lines in a background thread."""
import queue
import threading
import time

import serial


def parse_line(line):
    """'temp,hum,light,gas*XX' -> (t, h, l, g), or None if malformed / checksum fails."""
    payload, star, chk = line.strip().rpartition("*")
    if not star:
        return None
    try:
        if int(chk, 16) != _xor(payload):
            return None
        vals = tuple(float(p) for p in payload.split(","))
    except ValueError:
        return None
    return vals if len(vals) == 4 else None


def _xor(s):
    x = 0
    for ch in s.encode():
        x ^= ch
    return x


class SerialReader:
    """Auto-reconnecting reader. Same interface as simulator.SimulatedReader:
    .q (queue of (ts, t, h, l, g)), .connected, .send(cmd), .stop()."""

    def __init__(self, port, baud=115200, on_connect=None):
        self.port, self.baud = port, baud
        self.on_connect = on_connect          # called after each (re)connect
        self.q = queue.Queue()
        self.ser = None
        self.connected = False
        self.running = True
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.running:
            try:
                if self.ser is None or not self.ser.is_open:
                    ser = serial.Serial(self.port, self.baud, timeout=3)
                    time.sleep(2)             # ESP32 resets when the port opens
                    ser.reset_input_buffer()
                    self.ser = ser
                    self.connected = True
                    if self.on_connect:
                        self.on_connect()
                line = self.ser.readline().decode(errors="ignore").strip()
                vals = parse_line(line)
                if vals:
                    self.q.put((time.time(), *vals))
            except (serial.SerialException, OSError):
                self.connected = False
                with self._lock:
                    try:
                        if self.ser:
                            self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
                time.sleep(2)                 # retry

    def send(self, cmd: str):
        try:
            with self._lock:
                if self.ser and self.ser.is_open:
                    self.ser.write(cmd.encode())
        except (serial.SerialException, OSError):
            pass

    def stop(self):
        self.running = False
        with self._lock:
            try:
                if self.ser:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
        self.connected = False
