"""Project AURA dashboard (Streamlit). Display-only: all logic lives in engine.py."""
import datetime as dt
import random
import urllib.parse
from pathlib import Path

import altair as alt
import pandas as pd
import serial.tools.list_ports
import streamlit as st

from engine import ALERT, CALIBRATING, FEATURES, NORMAL, UNCALIBRATED, AuraEngine
from serial_reader import SerialReader
from simulator import SimulatedReader

SIM = "Simulator (no hardware)"
DATA_DIR = Path(__file__).parent / "data"
MUTED = "#9fb7c9"
SENSORS = [  # (feature key, title, icon, unit, colour, decimals)
    (FEATURES[0], "Temperature", "🌡️", "°C", "#ff9f5a", 1),
    (FEATURES[1], "Humidity", "💧", "%", "#4cc9f0", 0),
    (FEATURES[2], "Light", "☀️", "", "#ffd84d", 0),
    (FEATURES[3], "Air / Gas", "🌫️", "", "#b69cff", 0),
]
STATE_UI = {  # state -> (label, css colour var)
    NORMAL: ("NORMAL", "#38f2a0"),
    ALERT: ("ANOMALY", "#ff4d5e"),
    CALIBRATING: ("CALIBRATING", "#ffc857"),
    UNCALIBRATED: ("NOT CALIBRATED", "#7fa6c9"),
    "offline": ("DISCONNECTED", "#8c96a3"),
}
KIND_ICON = {"alert": "🔴", "normal": "🟢", "calibrating": "🟡", "calibrated": "✅", "error": "⚠️"}

st.set_page_config(page_title="Project AURA", page_icon="🌿", layout="wide")


# ---------------------------------------------------------------- look & feel
def landscape_svg() -> str:
    """Night forest + mountains + moon, generated in code (no image downloads)."""
    rnd = random.Random(7)
    w, h = 1600, 900
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice">',
         '<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0" stop-color="rgb(4,10,26)"/><stop offset="0.55" stop-color="rgb(8,46,66)"/>'
         '<stop offset="1" stop-color="rgb(18,96,96)"/></linearGradient>'
         '<radialGradient id="m"><stop offset="0" stop-color="rgb(210,255,240)" stop-opacity="0.85"/>'
         '<stop offset="1" stop-color="rgb(120,255,220)" stop-opacity="0"/></radialGradient>'
         '<filter id="b"><feGaussianBlur stdDeviation="40"/></filter></defs>',
         f'<rect width="{w}" height="{h}" fill="url(#s)"/>']
    for _ in range(140):  # stars
        p.append(f'<circle cx="{rnd.randint(0, w)}" cy="{rnd.randint(0, 420)}" r="{rnd.choice([1, 1, 1.5, 2])}" '
                 f'fill="rgb(235,250,255)" opacity="{rnd.uniform(.25, .9):.2f}"/>')
    p.append('<ellipse cx="520" cy="250" rx="520" ry="70" fill="rgb(60,255,170)" opacity="0.16" filter="url(#b)"/>')
    p.append('<ellipse cx="900" cy="190" rx="420" ry="50" fill="rgb(90,170,255)" opacity="0.14" filter="url(#b)"/>')
    p.append('<circle cx="1260" cy="170" r="170" fill="url(#m)"/>'
             '<circle cx="1260" cy="170" r="40" fill="rgb(236,255,246)" opacity="0.92"/>')

    def ridge(base, amp, fill, op):
        pts, y = [], base
        for x in range(0, w + 60, 60):
            y = max(base - amp, min(base + amp, y + rnd.uniform(-amp * .55, amp * .55)))
            pts.append(f"{x},{y:.0f}")
        p.append(f'<polygon points="0,{h} {" ".join(pts)} {w},{h}" fill="{fill}" opacity="{op}"/>')

    ridge(520, 120, "rgb(14,52,70)", 0.9)
    ridge(600, 90, "rgb(10,42,56)", 0.95)
    ridge(690, 70, "rgb(8,34,44)", 1)
    p.append(f'<path d="M0 760 Q 400 700 800 770 T 1600 740 L1600 900 L0 900 Z" fill="rgb(20,110,120)" opacity="0.35"/>')
    for x in range(-10, w + 30, 26):  # pine forest
        th = rnd.randint(70, 170)
        y0 = 900 - rnd.randint(0, 40)
        shade = rnd.choice(["rgb(4,22,28)", "rgb(5,28,32)", "rgb(3,18,24)"])
        p.append(f'<polygon points="{x},{y0} {x + 15},{y0 - th} {x + 30},{y0}" fill="{shade}"/>')
        p.append(f'<polygon points="{x + 3},{y0 - th * .45:.0f} {x + 15},{y0 - th * 1.12:.0f} {x + 27},{y0 - th * .45:.0f}" fill="{shade}"/>')
    p.append("</svg>")
    return "".join(p)


CSS = """
<style>
.stApp {
  background: linear-gradient(180deg, rgba(3,9,16,.30) 0%, rgba(3,9,16,.66) 100%),
              url("__BG__") center / cover fixed no-repeat;
  color: #dfeaf2;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] > div:first-child { background: rgba(6,16,26,.88); backdrop-filter: blur(10px); }
.block-container { padding-top: 1.4rem; max-width: 1320px; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(9,22,34,.62); border: 1px solid rgba(120,255,210,.16);
  border-radius: 16px; backdrop-filter: blur(9px);
  box-shadow: 0 6px 24px rgba(0,0,0,.28);
}
.brand { font-size: 2.0rem; font-weight: 800; letter-spacing: .12em; margin: 0; }
.brand span { color: #38f2a0; }
.tag { color: #9fb7c9; margin: -4px 0 12px; font-size: .92rem; }
.pill { display:inline-block; padding:3px 12px; border-radius:99px; font-size:.78rem; font-weight:700;
        border:1px solid currentColor; letter-spacing:.06em; }
.hero { display:flex; align-items:center; gap:22px; flex-wrap:wrap; padding:6px 4px; }
.pulse { width:54px; height:54px; border-radius:50%; background: var(--c); flex:none;
         box-shadow: 0 0 0 0 var(--c); animation: pulse 1.8s infinite; }
.hero-alert .pulse { animation-duration: .7s; }
@keyframes pulse { 0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--c) 70%,transparent);}
                   70%{box-shadow:0 0 0 24px transparent;} 100%{box-shadow:0 0 0 0 transparent;} }
.hero-title { font-size:2.1rem; font-weight:800; letter-spacing:.08em; color:var(--c); line-height:1.1; }
.hero-sub { color:#c5d6e3; font-size:.98rem; margin-top:2px; }
.hero-mid { flex:1 1 260px; min-width:240px; }
.ecg { flex:1 1 280px; height:64px; min-width:220px; color:var(--c); }
.ecg path { fill:none; stroke:currentColor; stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round;
            stroke-dasharray:520; stroke-dashoffset:520; animation: draw 2.6s linear infinite;
            filter: drop-shadow(0 0 4px currentColor); }
.hero-alert .ecg path { animation-duration: 1.1s; }
@keyframes draw { to { stroke-dashoffset: 0; } }
.kpis { display:flex; gap:22px; }
.kpi .v { font-size:1.7rem; font-weight:800; line-height:1.1; }
.kpi .l { font-size:.72rem; color:#9fb7c9; letter-spacing:.08em; text-transform:uppercase; }
.bar { height:8px; border-radius:6px; background:rgba(255,255,255,.12); overflow:hidden; margin-top:8px; }
.bar > div { height:100%; background:var(--c); border-radius:6px; transition:width .8s; }
.s-head { display:flex; justify-content:space-between; align-items:baseline; }
.s-name { color:#9fb7c9; font-size:.8rem; letter-spacing:.08em; text-transform:uppercase; }
.s-val { font-size:2.0rem; font-weight:800; line-height:1.1; }
.s-val small { font-size:.95rem; color:#9fb7c9; font-weight:600; }
.s-sub { font-size:.78rem; color:#9fb7c9; }
.ev { display:flex; gap:10px; padding:5px 2px; border-bottom:1px solid rgba(255,255,255,.07); font-size:.88rem; }
.ev .t { color:#8fa8ba; font-variant-numeric: tabular-nums; flex:none; }
.sec { font-size:.82rem; letter-spacing:.1em; text-transform:uppercase; color:#9fb7c9; margin:0 0 4px; }
</style>
"""
st.markdown(CSS.replace("__BG__", "data:image/svg+xml;utf8," + urllib.parse.quote(landscape_svg())),
            unsafe_allow_html=True)

ECG_PATH = ("M0 32 L40 32 L52 32 L60 30 L68 32 L96 32 L104 36 L112 6 L122 58 L132 28 L140 32 "
            "L176 32 L190 24 L204 32 L240 32 L252 32 L260 30 L268 32 L296 32 L304 36 L312 6 "
            "L322 58 L332 28 L340 32 L376 32 L390 24 L404 32 L440 32")


# ---------------------------------------------------------------- engine
@st.cache_resource
def _registry() -> dict:
    return {}


def get_engine(source: str) -> AuraEngine:
    """One engine per process, shared by every browser session. Switching the data
    source stops the old engine first so it releases the serial port."""
    reg = _registry()
    eng = reg.get(source)
    if eng is None:
        for old in reg.values():
            old.stop()
        reg.clear()
        if source == SIM:
            factory = lambda on_connect: SimulatedReader(interval=0.5, on_connect=on_connect)  # noqa: E731
        else:
            factory = lambda on_connect: SerialReader(source, on_connect=on_connect)  # noqa: E731
        eng = reg[source] = AuraEngine(factory, warmup_seconds=0 if source == SIM else 120)
    return eng


# ---------------------------------------------------------------- sidebar
ports = [p.device for p in serial.tools.list_ports.comports()]
options = ports + [SIM]
default = options.index(SIM) if st.query_params.get("source") == "sim" else 0
st.sidebar.markdown('<p class="brand" style="font-size:1.4rem">🌿 A<span>U</span>RA</p>', unsafe_allow_html=True)
source = st.sidebar.selectbox("Data source", options, index=default)
# Hardware sends one reading per 2 s and the model needs >= 30, so at least 90 s with margin.
cal_seconds = st.sidebar.number_input("Calibration length (s)", 20 if source == SIM else 90, 900,
                                      30 if source == SIM else 240, step=10)
eng = get_engine(source)
eng.cal_seconds = int(cal_seconds)

if st.sidebar.button("▶ Start calibration", type="primary", use_container_width=True):
    eng.start_calibration()
c_a, c_b = st.sidebar.columns(2)
if c_a.button("Reset", use_container_width=True):
    eng.reset()
if c_b.button("Load last", use_container_width=True, help="Reload the last saved calibration"):
    eng.load_saved_calibration()
sens = st.sidebar.slider("Sensitivity", 0.05, 0.40, float(eng.model.contamination), 0.05,
                         help="Higher = more sensitive (catches smaller changes, more "
                              "false alarms). 0.20 is the tuned default.")
if abs(sens - eng.model.contamination) > 1e-9:
    eng.set_contamination(sens)
window = st.sidebar.select_slider("Chart window", ["1 min", "2 min", "5 min", "All"], value="5 min")
WINDOW_S = {"1 min": 60, "2 min": 120, "5 min": 300, "All": 10**9}[window]
log = DATA_DIR / "readings.csv"
if log.exists():
    st.sidebar.download_button("⬇ Download readings (CSV)", log.read_bytes(),
                               file_name="aura_readings.csv", mime="text/csv", use_container_width=True)
st.sidebar.caption("Calibrate while the environment is normal, and vary light and temperature "
                   "through their usual range for a robust baseline.")
if source == SIM:
    st.sidebar.info("Simulator mode: synthetic data, no hardware.")
    kind = st.sidebar.selectbox("Inject anomaly", ["none", "dark", "humid", "hot", "gas", "combo"])
    eng.reader.inject(None if kind == "none" else kind)


# ---------------------------------------------------------------- charts
def _axis_y():
    return alt.Axis(title=None, labelColor=MUTED, gridColor="rgba(255,255,255,0.07)",
                    domain=False, tickCount=3, labelFontSize=10)


def _axis_x(show=True):
    return alt.Axis(title=None, labelColor=MUTED, grid=False, domain=False, tickCount=3,
                    format="%H:%M:%S", labelFontSize=10, labels=show, ticks=show,
                    labelOverlap="greedy", labelPadding=4)


MIN_SPAN = [1.0, 4.0, 150.0, 40.0]   # smallest visible y-range per sensor (keeps axes tidy)


def trace_chart(df, col, color, mean, tol, dec=0, min_span=1.0, height=110):
    """ECG-style trace: glow line, calibrated baseline band, red dots on anomalous readings."""
    d = df[["time", col, "anom"]].rename(columns={col: "v"})
    lo, hi = float(d.v.min()), float(d.v.max())
    if mean is not None:
        lo, hi = min(lo, mean - tol), max(hi, mean + tol)
    if hi - lo < min_span:                       # flat signal: widen so the axis stays readable
        mid = (hi + lo) / 2
        lo, hi = mid - min_span / 2, mid + min_span / 2
    pad = (hi - lo) * 0.12
    scale = alt.Scale(domain=[lo - pad, hi + pad], zero=False)
    y_axis = alt.Axis(title=None, labelColor=MUTED, gridColor="rgba(255,255,255,0.07)",
                      domain=False, tickCount=3, labelFontSize=10, format=f",.{dec}f")
    x, y = alt.X("time:T", axis=_axis_x()), alt.Y("v:Q", scale=scale, axis=y_axis)
    base = alt.Chart(d)
    layers = []
    if mean is not None:
        band = pd.DataFrame({"lo": [mean - tol], "hi": [mean + tol], "m": [mean]})
        layers.append(alt.Chart(band).mark_rect(color=color, opacity=0.11).encode(
            y=alt.Y("lo:Q", scale=scale), y2="hi:Q"))
        layers.append(alt.Chart(band).mark_rule(color=color, opacity=0.5, strokeDash=[4, 4]).encode(
            y=alt.Y("m:Q", scale=scale)))
    layers += [
        base.mark_line(color=color, strokeWidth=7, opacity=0.16, interpolate="monotone").encode(x, y),
        base.mark_line(color=color, strokeWidth=1.8, interpolate="monotone").encode(x, y),
        base.transform_filter("datum.anom").mark_point(color="#ff4d5e", filled=True, size=46,
                                                       opacity=0.95).encode(x, y),
    ]
    return alt.layer(*layers).properties(height=height).configure_view(strokeWidth=0)\
        .configure(background="transparent")


def score_chart(df):
    d = df.dropna(subset=["score"])
    if d.empty:
        return None
    x = alt.X("time:T", axis=_axis_x())
    y = alt.Y("score:Q", axis=_axis_y(), scale=alt.Scale(zero=False))
    b = alt.Chart(d)
    zero = alt.Chart(pd.DataFrame({"z": [0.0]})).mark_rule(color="#ff4d5e", strokeDash=[5, 4],
                                                           opacity=0.8).encode(y="z:Q")
    return alt.layer(
        b.mark_line(color="#38f2a0", strokeWidth=7, opacity=0.16, interpolate="monotone").encode(x, y),
        b.mark_line(color="#38f2a0", strokeWidth=1.8, interpolate="monotone").encode(x, y),
        b.transform_filter("datum.score < 0").mark_point(color="#ff4d5e", filled=True, size=40).encode(x, y),
        zero,
    ).properties(height=150).configure_view(strokeWidth=0).configure(background="transparent")


def deviation_chart(z):
    names = [s[1] for s in SENSORS]
    d = pd.DataFrame({"Sensor": names, "z": [max(-8.0, min(8.0, v)) for v in z], "raw": z})
    d["col"] = d.raw.abs().map(lambda v: "#ff4d5e" if v >= 3 else ("#ffc857" if v >= 1.5 else "#38f2a0"))
    bars = alt.Chart(d).mark_bar(cornerRadius=4, height=16).encode(
        y=alt.Y("Sensor:N", sort=names, axis=alt.Axis(title=None, labelColor="#dfeaf2", domain=False, ticks=False)),
        x=alt.X("z:Q", scale=alt.Scale(domain=[-8, 8]),
                axis=alt.Axis(title="deviation from baseline (σ)", titleColor=MUTED, labelColor=MUTED,
                              gridColor="rgba(255,255,255,0.07)", tickCount=5, domain=False)),
        color=alt.Color("col:N", scale=None))
    return bars.properties(height=150).configure_view(strokeWidth=0).configure(background="transparent")


# ---------------------------------------------------------------- live view
def hero(s, cause):
    state = "offline" if not s["connected"] else s["state"]
    label, color = STATE_UI[state]
    if state == "offline":
        sub = "Trying to reconnect to the ESP32…"
    elif state == CALIBRATING:
        sub = f"Learning what normal looks like: {s['cal_left']} s left · {s['n_cal']} samples"
    elif state == UNCALIBRATED and s["warmup_left"] > 0:
        sub = f"Gas sensor warming up: calibration available in {s['warmup_left']} s"
    elif state == UNCALIBRATED:
        sub = "Open the sidebar and press Start calibration"
    elif state == ALERT:
        sub = "Unusual pattern" + (f": {cause}" if cause else "")
    else:
        sub = "All sensors match the calibrated pattern"
    prog = ""
    if state == CALIBRATING and eng.cal_seconds:
        pct = max(0, min(100, 100 * (1 - s["cal_left"] / eng.cal_seconds)))
        prog = f'<div class="bar"><div style="width:{pct:.0f}%"></div></div>'
    health = "n/a"
    if s["score"] is not None and state in (NORMAL, ALERT):
        health = f"{max(0, min(100, (s['score'] + 0.15) / 0.30 * 100)):.0f}%"
    st.markdown(
        f'<div class="hero hero-{state}" style="--c:{color}">'
        f'<div class="pulse"></div>'
        f'<div class="hero-mid"><div class="hero-title">{label}</div><div class="hero-sub">{sub}</div>{prog}</div>'
        f'<svg class="ecg" viewBox="0 0 440 64" preserveAspectRatio="none"><path d="{ECG_PATH}"/></svg>'
        f'<div class="kpis"><div class="kpi"><div class="v" style="color:{color}">{health}</div>'
        f'<div class="l">Environment health</div></div>'
        f'<div class="kpi"><div class="v">{s["alert_count"]}</div><div class="l">Alerts this session</div></div></div>'
        f'</div>', unsafe_allow_html=True)


@st.fragment(run_every=1)
def live():
    s = eng.snapshot()
    z, base = s["z"], s["baseline"]
    cause = ""
    if z:
        top = sorted(zip([x[1] for x in SENSORS], z), key=lambda p: -abs(p[1]))[:2]
        cause = ", ".join(f"{n} {v:+.1f}σ" for n, v in top if abs(v) >= 1.5)

    with st.container(border=True):
        hero(s, cause)
    if s["message"]:
        st.error(s["message"])
    if not s["data"]:
        st.caption("Waiting for data from the sensors…")
        return

    df = pd.DataFrame(s["data"])
    df["time"] = [dt.datetime.fromtimestamp(t) for t in df["time"]]
    df = df[df["time"] >= df["time"].iloc[-1] - dt.timedelta(seconds=WINDOW_S)]
    last = df.iloc[-1]

    cols = st.columns(4)
    for i, (key, title, icon, unit, color, dec) in enumerate(SENSORS):
        with cols[i], st.container(border=True):
            val = last[key]
            mean = base["mean"][i] if base else None
            tol = base["sigma"][i] if base else 0
            sub = "baseline pending" if mean is None else f"baseline {mean:.{dec}f}{unit} · Δ {val - mean:+.{dec}f}"
            st.markdown(
                f'<div class="s-head"><span class="s-name">{icon} {title}</span></div>'
                f'<div class="s-val" style="color:{color}">{val:.{dec}f}<small> {unit}</small></div>'
                f'<div class="s-sub">{sub}</div>', unsafe_allow_html=True)
            st.altair_chart(trace_chart(df, key, color, mean, tol, dec, MIN_SPAN[i]),
                            use_container_width=True, theme=None)

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.markdown('<p class="sec">Anomaly score · below the red line = unusual</p>', unsafe_allow_html=True)
        ch = score_chart(df)
        if ch is not None:
            st.altair_chart(ch, use_container_width=True, theme=None)
        else:
            st.caption("The score appears after calibration.")
    with right, st.container(border=True):
        st.markdown('<p class="sec">Which sensor is off?</p>', unsafe_allow_html=True)
        if z:
            st.altair_chart(deviation_chart(z), use_container_width=True, theme=None)
        else:
            st.caption("Deviation bars appear after calibration.")

    with st.container(border=True):
        st.markdown('<p class="sec">Event log</p>', unsafe_allow_html=True)
        evs = list(reversed(s["events"]))[:10]
        if not evs:
            st.caption("No events yet.")
        for e in evs:
            t = dt.datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
            st.markdown(f'<div class="ev"><span class="t">{t}</span><span>{KIND_ICON.get(e["kind"], "•")} '
                        f'{e["text"]}</span></div>', unsafe_allow_html=True)


st.markdown('<p class="brand">PROJECT A<span>U</span>RA</p>'
            '<p class="tag">Intelligent multisensor environmental anomaly detection · '
            'Isolation Forest · live from ESP32</p>', unsafe_allow_html=True)
live()
st.caption("Prototype for monitoring and anomaly detection, not a certified safety or pollution instrument. "
           "An anomaly means \"unusual compared with the calibration\", not \"dangerous\".")
