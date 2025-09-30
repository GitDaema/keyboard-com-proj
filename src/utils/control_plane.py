from __future__ import annotations

"""
Control-plane: read key LED colors and map to CPU actions.

Keys and roles (by label):
  - grave: RUN/PAUSE/HALT/FAULT (fault = red blink)
  - esc:   RESET (blue) / E-HALT (red)
  - tab:   Step mode (off=continuous, white=instr, pink=micro)
  - caps_lock: Trace (off=off, cyan=on, yellow=marker)
  - left_shift: Overlay/Service (yellow=ALU, blue=IRPC, purple=BUS, cyan=SERVICE)

This module provides a light-weight, sample-and-decide reader with
short memory (for blink detection and debounce). It avoids sleeps;
callers should invoke poll() regularly (e.g., each run-loop tick).
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Literal, Any
import time

from rgb_controller import get_key_color, set_key_color
import utils.color_presets as cp
from utils.ir_indicator import calibrate_ir
from utils.keyboard_presets import (
    RUN_PAUSE_LABEL,
    KEY_ESC_LABEL,
    KEY_TAB_LABEL,
    KEY_CAPS_LABEL,
    KEY_LSHIFT_LABEL,
)

# ---- Enums (string Literals keep deps minimal) ----
RunState = Literal["RUN", "PAUSE", "HALT", "FAULT"]
EscState = Literal["NONE", "RESET", "EHALT"]
StepMode = Literal["CONT", "INSTR", "MICRO"]
TraceState = Literal["OFF", "ON", "MARK"]
OverlayMode = Literal["NONE", "ALU", "IRPC", "BUS", "SERVICE"]


def _rgb_tuple(c: Any | Tuple[int, int, int]) -> Tuple[int, int, int]:
    try:
        # cp constants are RGBColor; convert to (r,g,b)
        return (int(c.red), int(c.green), int(c.blue))  # type: ignore[attr-defined]
    except Exception:
        t = tuple(int(x) for x in c)  # already a tuple
        return (t[0], t[1], t[2])


_PALETTE = {
    # grave
    "RUN": _rgb_tuple(cp.GREEN),
    "PAUSE": _rgb_tuple(cp.ORANGE),
    "HALT": _rgb_tuple(cp.RED),
    # blink detection for FAULT uses HALT vs BLACK alternation
    "OFF": _rgb_tuple(cp.BLACK),
    # esc
    "RESET": _rgb_tuple(cp.BLUE),
    "EHALT": _rgb_tuple(cp.RED),
    # tab
    "INSTR": _rgb_tuple(cp.WHITE),
    "MICRO": _rgb_tuple(cp.PINK),
    # caps
    "TRACE": _rgb_tuple(cp.CYAN),
    "MARK": _rgb_tuple(cp.YELLOW),
    # lshift
    "ALU": _rgb_tuple(cp.BRIGHT_YELLOW if hasattr(cp, "BRIGHT_YELLOW") else cp.YELLOW),
    "IRPC": _rgb_tuple(cp.BLUE),
    "BUS": _rgb_tuple(cp.PURPLE),
    "SERVICE": _rgb_tuple(cp.CYAN),
}


def _d2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return dr * dr + dg * dg + db * db


def _nearest(label: str, candidates: Dict[str, Tuple[int, int, int]]) -> str:
    r, g, b = get_key_color(label, fresh=True)[0]
    cur = (int(r), int(g), int(b))
    best_k = next(iter(candidates))
    best_d = 10 ** 12
    for k, col in candidates.items():
        d = _d2(cur, col)
        if d < best_d:
            best_d = d
            best_k = k
    return best_k


# Short history buffer for blink detection and debounce
_HIST: Dict[str, list[Tuple[float, Tuple[int, int, int]]]] = {}


def _push_hist(label: str, rgb: Tuple[int, int, int], keep: int = 6) -> None:
    arr = _HIST.get(label) or []
    arr.append((time.time(), rgb))
    if len(arr) > keep:
        del arr[0 : len(arr) - keep]
    _HIST[label] = arr


def _read_rgb(label: str) -> Tuple[int, int, int]:
    r, g, b = get_key_color(label, fresh=True)[0]
    rgb = (int(r), int(g), int(b))
    _push_hist(label, rgb)
    return rgb


def _is_blinking_red(label: str) -> bool:
    arr = _HIST.get(label) or []
    if len(arr) < 3:
        return False
    # Consider blinking if recent samples alternate between near RED and near BLACK
    red = _PALETTE["HALT"]
    off = _PALETTE["OFF"]
    hit_red = 0
    hit_off = 0
    for _, rgb in arr[-4:]:
        if _d2(rgb, red) < 6000:
            hit_red += 1
        if _d2(rgb, off) < 4000:
            hit_off += 1
    return hit_red >= 1 and hit_off >= 1


@dataclass
class ControlStates:
    run: RunState = "PAUSE"
    esc: EscState = "NONE"
    step: StepMode = "CONT"
    trace: TraceState = "OFF"
    overlay: OverlayMode = "NONE"


_SERVICE_COOLDOWN_S = 2.0
_last_service_ts: float | None = None


def poll() -> ControlStates:
    """Sample keys and classify their states into enums."""
    st = ControlStates()

    # --- grave ---
    rgb_g = _read_rgb(RUN_PAUSE_LABEL)
    # Decide RUN/PAUSE/HALT by nearest color; FAULT by blink pattern
    rn = _nearest(
        RUN_PAUSE_LABEL,
        {
            "RUN": _PALETTE["RUN"],
            "PAUSE": _PALETTE["PAUSE"],
            "OFF": _PALETTE["OFF"],
            "HALT": _PALETTE["HALT"],
        },
    )
    if _is_blinking_red(RUN_PAUSE_LABEL):
        st.run = "FAULT"
    else:
        st.run = ("PAUSE" if rn in ("PAUSE", "OFF") else rn)  # type: ignore[assignment]

    # --- esc ---
    rgb_e = _read_rgb(KEY_ESC_LABEL)
    # nearest among red/blue/off
    esc_sel = _nearest(
        KEY_ESC_LABEL,
        {"EHALT": _PALETTE["EHALT"], "RESET": _PALETTE["RESET"], "NONE": _PALETTE["OFF"]},
    )
    st.esc = esc_sel  # type: ignore[assignment]

    # --- tab ---
    _read_rgb(KEY_TAB_LABEL)
    tab_sel = _nearest(
        KEY_TAB_LABEL,
        {"INSTR": _PALETTE["INSTR"], "MICRO": _PALETTE["MICRO"], "CONT": _PALETTE["OFF"]},
    )
    st.step = tab_sel  # type: ignore[assignment]

    # --- caps ---
    _read_rgb(KEY_CAPS_LABEL)
    caps_sel = _nearest(
        KEY_CAPS_LABEL,
        {"ON": _PALETTE["TRACE"], "MARK": _PALETTE["MARK"], "OFF": _PALETTE["OFF"]},
    )
    st.trace = caps_sel  # type: ignore[assignment]

    # --- left_shift ---
    _read_rgb(KEY_LSHIFT_LABEL)
    shift_sel = _nearest(
        KEY_LSHIFT_LABEL,
        {
            "ALU": _PALETTE["ALU"],
            "IRPC": _PALETTE["IRPC"],
            "BUS": _PALETTE["BUS"],
            "SERVICE": _PALETTE["SERVICE"],
            "NONE": _PALETTE["OFF"],
        },
    )
    st.overlay = shift_sel  # type: ignore[assignment]

    return st


def maybe_run_service(st: ControlStates) -> bool:
    """Run one-shot service tasks (e.g., IR calibration) when requested.
    Returns True if a service ran.
    """
    global _last_service_ts
    if st.overlay != "SERVICE":
        return False
    now = time.time()
    if _last_service_ts is not None and (now - _last_service_ts) < _SERVICE_COOLDOWN_S:
        return False
    try:
        calibrate_ir(samples=2, settle_ms=8, debug=False)
    except Exception:
        pass
    _last_service_ts = now
    return True


# ---------- Setters: code-driven switch control (like physical panel) ----------

def set_run_state(state: RunState, *, use_orange_pause: bool = False) -> None:
    if state == "RUN":
        col = _PALETTE["RUN"]
    elif state == "HALT":
        col = _PALETTE["HALT"]
    elif state == "FAULT":
        col = _PALETTE["HALT"]  # indicate with red; blink not handled here
    else:  # PAUSE
        col = _PALETTE["PAUSE"] if use_orange_pause else _PALETTE["OFF"]
    try:
        set_key_color(RUN_PAUSE_LABEL, cp.RGBColor(*col))
    except Exception:
        pass


def set_esc_state(state: EscState) -> None:
    if state == "RESET":
        col = _PALETTE["RESET"]
    elif state == "EHALT":
        col = _PALETTE["EHALT"]
    else:
        col = _PALETTE["OFF"]
    try:
        set_key_color(KEY_ESC_LABEL, cp.RGBColor(*col))
    except Exception:
        pass


def set_step_mode(mode: StepMode) -> None:
    if mode == "INSTR":
        col = _PALETTE["INSTR"]
    elif mode == "MICRO":
        col = _PALETTE["MICRO"]
    else:
        col = _PALETTE["OFF"]
    try:
        set_key_color(KEY_TAB_LABEL, cp.RGBColor(*col))
    except Exception:
        pass


def set_trace_state(state: TraceState) -> None:
    if state == "ON":
        col = _PALETTE["TRACE"]
    elif state == "MARK":
        col = _PALETTE["MARK"]
    else:
        col = _PALETTE["OFF"]
    try:
        set_key_color(KEY_CAPS_LABEL, cp.RGBColor(*col))
    except Exception:
        pass


def set_overlay_mode(mode: OverlayMode) -> None:
    if mode == "ALU":
        col = _PALETTE["ALU"]
    elif mode == "IRPC":
        col = _PALETTE["IRPC"]
    elif mode == "BUS":
        col = _PALETTE["BUS"]
    elif mode == "SERVICE":
        col = _PALETTE["SERVICE"]
    else:
        col = _PALETTE["OFF"]
    try:
        set_key_color(KEY_LSHIFT_LABEL, cp.RGBColor(*col))
    except Exception:
        pass


def init_default_panel() -> None:
    """Initialize control LEDs to a known default like a physical panel.
    - grave: PAUSE (off by default)
    - esc: off
    - tab: CONT (off)
    - caps: OFF
    - left_shift: NONE (off)
    """
    set_run_state("PAUSE", use_orange_pause=False)
    set_esc_state("NONE")
    set_step_mode("CONT")
    set_trace_state("OFF")
    set_overlay_mode("NONE")
