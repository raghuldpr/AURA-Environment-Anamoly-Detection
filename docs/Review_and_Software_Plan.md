# Project AURA: Spec Review, Corrections and Software Plan

> **Note (later changes):** this review was written before implementation. The build then moved to a DHT11, an MH-series LDR *module*, an MQ-135 gas sensor (4 sensors total), a checksum on every serial line, and a retuned model (noise floors + a 0.20 sensitivity threshold instead of `contamination=0.03`). See the main [README](../README.md) and the [Wiring Guide](Wiring_Guide.md) for the final state.

Reviewed file: `Project_AURA_Implementation_Guide.md`
Verdict: the concept, pin map and firmware are sound. The **Python side has several real bugs** (mostly from tying the serial port and the alert logic to Streamlit's session), and the **buzzer advice contradicts itself**. All are fixed in the plan below.

---

## 1. Findings

### A. Software bugs (fix before coding)

| # | Severity | Where | Problem | Correction |
|---|---|---|---|---|
| A1 | **High** | 6.3 `app.py` | `SerialReader` lives in `st.session_state`. Refreshing the page or opening a second tab creates a new session, so a **second reader tries to open the same COM port** ("Access denied") while the old thread (daemon, never stopped) still holds it. The model and calibration are also lost on every refresh. | One process-wide **engine** created with `st.cache_resource`. It owns the serial thread, the model and all state. Sessions only display it. |
| A2 | **High** | 6.3 | Scoring, debounce and the traffic-light commands run inside the Streamlit script loop. If the tab is closed, minimised or throttled, **alerts stop** and the light freezes. | Move ingest, calibration timer, scoring, debounce and `send()` into the engine's background thread. The dashboard is display-only. |
| A3 | Medium | 6.1 + 5.2 | Opening the port **resets the ESP32** (DTR/RTS), which returns it to yellow. The app still believes it is "Normal" or "Alert", so the light and the dashboard disagree until the state changes. | Engine re-sends the current state on every (re)connect **and as a 2 s heartbeat**. |
| A4 | Medium | 5.2 | If the app crashes or the cable is pulled, the ESP32 **keeps the last state forever** (a red + buzzer alarm can stick on). | Firmware failsafe: if no command arrives for 10 s, fall back to yellow ("not monitored"). |
| A5 | Medium | 6.3 | `time.sleep(1); st.rerun()` re-runs the whole script every second: flicker, and sidebar clicks lag up to 1 s. | Use `@st.fragment(run_every=1)` for the live area. |
| A6 | Low | 6.3 | Chart x-axis is raw epoch floats (`1.7e9`), unreadable. | Convert to `datetime`. |
| A7 | Low | 6.3 | If calibration ends with fewer than 30 samples, nothing happens and no message is shown. | Show an explicit "Calibration failed: only N samples" and stay un-calibrated. |
| A8 | Low | 6.3 | No way to recalibrate cleanly or keep the model after a restart. | Add Recalibrate / Reset buttons. Save the calibration data to `data/` so a restart can reload it. Log every reading to CSV (useful for the report). |

### B. Hardware and spec issues

| # | Severity | Where | Problem | Correction |
|---|---|---|---|---|
| B1 | **Medium** | 3.5 | Says an ESP32 pin supplies "about 12–40 mA", then recommends a ~30 mA buzzer wired **directly** to the pin. The ESP32's recommended per-pin current is about 12 mA (40 mA is the absolute maximum). | Drive the buzzer through an **NPN transistor** (BC547 + 1.5 kΩ or 220 Ω base resistor), unless it is a 3-pin buzzer *module* with its own transistor. Direct drive is acceptable only for a ≤ 12 mA buzzer. |
| B2 | Medium | 3.3 | ESP32 ADC reads ~0 below roughly 0.1 V (about the first 100–150 counts). With a 1.5 kΩ resistor, dim light can fall inside that dead zone and look flat. The guide's quick check is right, but it understates why. | Keep 1.5 kΩ, **do the quick check at wiring time**, and swap to 4.7–10 kΩ if normal room light reads below ~500. No code change needed. |
| B3 | Low | 3.2 | DHT22 bare-sensor pin order is never given, and the ESP32 internal pull-up (~45 kΩ) is weak. | Pin order added to the wiring guide. If readings are NaN, add a 4.7–10 kΩ DATA→3.3 V pull-up. |
| B4 | Low | 3.4 | Traffic module resistors are usually sized for 5 V, so LEDs are dimmer at 3.3 V logic. Not a fault. | No change. Check the module has no VCC pin before powering it. |

### C. Spec and report wording

| # | Where | Issue | Correction |
|---|---|---|---|
| C1 | 1.7 / 12 | Isolation Forest scores anything **outside the range seen in calibration** as unusual. Slow, legitimate drift (room warming over the day, daylight changing) will eventually raise alerts. This is not listed as a limitation. | Add to Limitations: "calibrate across the normal range; recalibrate when conditions change". The Recalibrate button covers this. |
| C2 | 7 (Demo tip) | The "individually normal, combined unusual" demo works only if temperature and light actually **vary together** during calibration. | Keep the tip, and make the demo script explicit: warm + bright during calibration, then show dim + warm. |
| C3 | 4.3 | Layout assumes a new `project-aura/` folder. | Use the existing folder `C:\Users\raghu\Desktop\AI R\` as the project root. |

Checked and **no problem found**: pin choices (no strapping pins, ADC1 for analog), LDR divider polarity (brighter = higher value), 2 s DHT22 interval, `Serial.printf` on ESP32, CSV line format, boot-banner lines being ignored by the parser, no scaling needed for Isolation Forest, contamination/debounce arithmetic.

---

## 2. Corrected architecture

```
DHT22 + LDR -> ESP32 --USB serial 115200--> SerialReader thread
                                              |
                                        AuraEngine (one per process, background thread)
                                        - calibration timer + buffer
                                        - IsolationForest fit / score
                                        - 3-in-a-row debounce
                                        - sends 0/1/2 on change + every 2 s heartbeat
                                        - appends every reading to data/readings.csv
                                              |
                              Streamlit (st.cache_resource -> engine)
                              display-only, fragment refresh every 1 s
```

Traffic light: **green = normal, yellow = calibrating / not calibrated / app silent, red + buzzer = anomaly.**

---

## 3. Software plan

Project root: `C:\Users\raghu\Desktop\AI R\`

```
AI R/
├── aura-firmware/        platformio.ini, src/main.cpp
├── aura-app/
│   ├── serial_reader.py  serial thread, parse, auto-reconnect, send()
│   ├── model.py          AuraModel: fit / score / save / load
│   ├── engine.py         AuraEngine: calibration, scoring, debounce, heartbeat, CSV log
│   ├── simulator.py      fake ESP32 source (no hardware needed)
│   ├── app.py            Streamlit dashboard
│   ├── tests/            pytest: model + engine (with simulator)
│   ├── data/             readings.csv, calibration.csv (created at run time)
│   └── requirements.txt
└── docs/
```

| Step | Work | Done when |
|---|---|---|
| S1 | Check Python, create `venv`, `requirements.txt`, install | `pip list` shows streamlit, pyserial, scikit-learn, pandas, numpy |
| S2 | **Firmware first** (you need it for wiring tests): `platformio.ini`, `main.cpp` with the 10 s failsafe | Builds with `pio run` |
| S3 | `serial_reader.py` with reconnect, state re-send hook, and a `simulator.py` drop-in with the same interface | Reader yields tuples from either source |
| S4 | `model.py` with a minimum-samples check, save/load | Unit tests pass |
| S5 | `engine.py` (thread-safe snapshot for the UI) | Tests: calibrate on simulated normal data, anomaly flagged after 3 readings, green again after recovery |
| S6 | `app.py`: port picker (+ "Simulator" option), status banner, metrics, charts with real timestamps, Start calibration / Recalibrate, sensitivity slider | Runs headless, checked in the browser pane |
| S7 | End-to-end test with the simulator (all of test-plan items 4–9 in software) | Screenshots and logs |
| S8 | **With hardware:** upload firmware via PlatformIO, check traffic light with `0`/`1`/`2`, then run the real app | Test plan items 1–10 |

Hardware-independent steps S1–S7 can be finished while you wire. S8 needs your wiring done.

---

## 4. Things I will check on your machine rather than ask

- Python version and whether PlatformIO (`pio`) is on PATH or only inside VS Code.
- Which COM port the ESP32 appears on (needs it plugged in).

## 5. Needed from you when you reach the bench

- Whether you got a **small active buzzer** or a bare/large one (decides the transistor wiring).
- The LDR quick-check numbers (bright / room / covered).
- Whether the traffic-light module has any pin other than GND, R, Y, G.
