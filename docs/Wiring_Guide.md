# Project AURA: Hardware Wiring Guide

**Rule 1:** USB unplugged while you wire. Plug in only to test.
**Rule 2:** Build and test one part at a time, in the order below.
**Rule 3:** All parts share one ground. Never put 5 V on a GPIO pin.

Pin labels on ESP32 boards vary ("D4", "G4", "GPIO4", "4"). They all mean the same GPIO number. Match on the number.

## 1. Pin map (final)

| Part | Part pin | ESP32 pin |
|---|---|---|
| DHT22 | VCC | 3V3 |
| DHT22 | DATA | **GPIO4** |
| DHT22 | GND | GND |
| LDR module (MH series) | VCC | 3V3 |
| LDR module (MH series) | GND | GND |
| LDR module (MH series) | AO (analog) | **GPIO34** |
| LDR module (MH series) | DO (digital) | not connected |
| Traffic light | GND | GND |
| Traffic light | R | **GPIO27** |
| Traffic light | Y | **GPIO25** |
| Traffic light | G | **GPIO26** |
| MQ gas sensor | VCC | **VIN (5 V)**, not 3V3 |
| MQ gas sensor | GND | GND |
| MQ gas sensor | AO (analog) | **GPIO35**, **through a voltage divider** (step 4) |
| MQ gas sensor | DO (digital) | not connected |
| Buzzer (attach later) | (+) / signal | **GPIO33** (see step 5 for the safe wiring) |

Do not use GPIO0, 2, 12, 15 (boot pins), and do not move the LDR off GPIO34 (analog input, ADC1).

## 2. Power rails

1. ESP32 **3V3** pin → breadboard **+ rail**.
2. ESP32 **GND** pin → breadboard **− rail**.

## 3. Wiring, one part at a time

### Step 1: DHT11 / DHT22 (temperature and humidity)

> **This build uses a DHT11** (firmware `DHTTYPE DHT11`). Wiring is identical to the DHT22 below. The DHT11 reads in whole degrees (about ±2 °C) and 20–80 % humidity, which is fine for anomaly detection, but its values step in whole numbers.

**Bare 4-pin sensor.** Hold it with the grid/vent side facing you, pins down. Left to right:

```
 pin 1   pin 2   pin 3   pin 4
 VCC     DATA    (NC)    GND
```

- Pin 1 → + rail (3V3)
- Pin 2 → **GPIO4**
- Pin 3 → leave empty
- Pin 4 → − rail (GND)

**3-pin module:** read the print on the board (`+`, `OUT`, `-`). `+` → 3V3, OUT → GPIO4, `-` → GND. No resistor.

If the serial monitor later shows no readings (NaN): add a **4.7–10 kΩ resistor between DATA and 3V3** (bare sensor only). Do **not** use 220 Ω.

### Step 2: LDR module (light), 4 pins: VCC, GND, DO, AO

Your module (MH sensor series) already has the LDR and its resistor divider on the board, so **no resistor is needed**.

- Module **VCC → 3V3** (use **3V3, not 5 V**, so AO can never exceed what the ESP32 accepts)
- Module **GND → GND**
- Module **AO → GPIO34**
- Module **DO → leave unconnected** (on/off output set by the blue potentiometer; the AI does not use it)

The reading direction depends on the module: on some, brighter light gives a **higher** value, on others **lower**. Either is fine, since the model only learns what is normal. Just note which way yours goes.

### Step 3: Traffic-light module

- Module **GND** → − rail
- Module **R** → **GPIO27**
- Module **Y** → **GPIO25**
- Module **G** → **GPIO26**

The resistors are already on the module, so add none. **If the module has any extra pin (VCC, 5V, +), stop and tell me before connecting it.**

### Step 4: MQ gas sensor (4-pin module: VCC, GND, DO, AO)

**Why it needs care:** the MQ heater needs **5 V**, and the AO pin can swing up to **5 V**. ESP32 pins are 3.3 V only, so **AO must go through a voltage divider** or you can damage GPIO35.

```
MQ AO ──[ R1 ]──┬── GPIO35
                │
              [ R2 ]
                │
               GND
```

- **R1 = R2.** Best: **10 kΩ + 10 kΩ** (max 2.5 V at the pin). If you only have the small resistors, **two 1.5 kΩ** also work and are safe, but they load the sensor output a bit and reduce the reading range. Do **not** use the 220 Ω for this.
- MQ **VCC → VIN** (the 5 V pin, powered from USB). **Not** 3V3.
- MQ **GND → GND**.
- **DO: leave unconnected.** It is a 5 V on/off signal set by the blue potentiometer; the AI does not use it.
- **Keep the 5 V and 3V3 rails separate on the breadboard.** Use a different rail (or jumper wire) for VIN. Never join them.
- **GPIO35** is analog-only (ADC1), which is what we want.

**Facts to know:**
- The heater draws about 150 mA and the sensor body gets **hot**. Keep it away from wires and anything flammable.
- It needs a warm-up (the dashboard enforces **120 s** before you can calibrate; a longer warm-up of several minutes is better, and a brand-new sensor drifts for hours).
- Readings are **relative** (raw 0–4095), not ppm. Which gas it responds to depends on the model (MQ-2 smoke/LPG, MQ-135 air quality, etc.). Tell me the model number printed on it.

### Step 5: Buzzer (attach later, optional)

The system works without it. The firmware already drives GPIO33, so leave that pin empty until you have the buzzer. Pick one. Check which you have:

**A. 3-pin buzzer module** (has `VCC`, `GND`, `I/O` or `S`): VCC → 3V3, GND → GND, I/O → **GPIO33**. Done.

**B. Small bare active buzzer (2 legs, + marked)**, recommended wiring with an NPN transistor (BC547 or similar):

```
GPIO33 ──[ 1.5 kΩ ]── Base
                      BC547 (flat side facing you, pins down):
                        left = Collector, middle = Base, right = Emitter
Emitter   → GND (− rail)
Collector → buzzer (−)
Buzzer (+) → 3V3 (+ rail)
```

Use a **1.5 kΩ** (you will have spares now that the LDR needs none) or the **220 Ω** as the base resistor.

**C. Direct (only for a demo, small risk):** buzzer (+) → GPIO33, (−) → GND. Use only if the buzzer is rated about 12 mA or less. If the ESP32 resets or the sound is weak when it sounds, switch to B.

**Do not use the bike/two-wheeler horn.** It is a 12 V, amp-level device.

## 4. Bring-up checks

Plug in USB. Each check needs the firmware uploaded (we do that together in VS Code with PlatformIO).

| Check | What you do | Expected |
|---|---|---|
| 1. Boot | Open the PlatformIO serial monitor at 115200 | Yellow LED on. Lines like `27.4,61.2,1830,410` every 2 s (temp, humidity, light, gas) |
| 2. DHT22 | Breathe gently on it | Humidity and temperature rise |
| 3. LDR | Note the third number in: bright light, normal room light, covered | Three clearly different values. **Write them down.** |
| 3b. Gas | After a few minutes of warm-up, hold an alcohol wipe or hand sanitizer (no flame, no gas) near it | Gas value rises clearly. Write down the clean-air value |
| 4. Lights | Type `0`, `1`, `2` in the monitor | `0` green, `1` red (+ buzzer), `2` yellow |
| 5. Failsafe | After sending `1`, wait about 10 s | Falls back to yellow |

**LDR check:** the three values (bright, room, covered) should be clearly different. If they barely change, turn the blue potentiometer on the module slightly and retry. No code change needed.

## 5. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Port not listed | Charge-only cable, or missing CP210x/CH340 driver |
| Upload stuck on "Connecting…" | Hold **BOOT** until it starts |
| No readings, nothing printed | DHT22 wiring or pin order; add the pull-up |
| Light number never changes | AO wire not on GPIO34, or module VCC/GND not connected (its power LED should be lit) |
| Light number stuck at 0 or 4095 | Adjust the blue potentiometer; check you used AO, not DO |
| One traffic colour dead | Check R/Y/G order against the module's printed labels |
| Board resets when the buzzer sounds | Use the transistor wiring (B) |
| "Access denied" in the app | Close the PlatformIO serial monitor first (only one program can hold the port) |

## 6. Before you tell me "wiring done"

- [ ] USB cable is a data cable
- [ ] 3V3 and GND rails connected and every part grounded
- [ ] DHT22 DATA on GPIO4, LDR module AO on GPIO34 (module VCC on 3V3)
- [ ] Traffic R/Y/G on 27/25/26, traffic GND on GND
- [ ] MQ VCC on VIN (5 V), AO through the divider to GPIO35, DO unconnected
- [ ] 5 V and 3V3 rails not joined
- [ ] No 5 V on any GPIO (AO goes only through the divider)
