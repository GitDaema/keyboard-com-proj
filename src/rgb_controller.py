"""RGB controller facade decoupled from external programs.

Default backend: Direct HID (no OpenRGB required).
"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple

from rgb_types import RGBColor
from config import MAPS_DIR
from utils.keyboard_map import RGBLabelController

from backends.base import RGBBackend, NoopBackend
try:
    from backends.direct_hid_backend import DirectHIDBackend
except Exception:
    DirectHIDBackend = None  # type: ignore

# Global state
_backend: Optional[RGBBackend] = None
km: Optional[RGBLabelController] = None

# Runtime toggles
_ATOMIC_DEBUG: bool = False
_APPLY_DELAY_MS: int = 20  # settle after updates (ms)
_GROUP_ATOMIC: bool = False

# Cache to skip no-op writes (label -> (r,g,b))
_LAST_LABEL_COLOR: Dict[str, Tuple[int, int, int]] = {}

__all__ = [
    'connect', 'disconnect', 'is_connected',
    'get_key_color', 'set_key_color', 'set_labels_atomic',
    'init_all_keys', 'set_apply_delay_ms', 'set_atomic_debug',
    'set_group_atomic', 'is_group_atomic'
]


# --- Runtime toggles ---

def set_atomic_debug(on: bool) -> None:
    global _ATOMIC_DEBUG
    _ATOMIC_DEBUG = bool(on)


def set_group_atomic(on: bool) -> None:
    global _GROUP_ATOMIC
    _GROUP_ATOMIC = bool(on)


def is_group_atomic() -> bool:
    return bool(_GROUP_ATOMIC)


def set_apply_delay_ms(ms: int) -> None:
    global _APPLY_DELAY_MS
    try:
        m = int(ms)
    except Exception:
        return
    if m < 5:
        m = 5
    if m > 40:
        m = 40
    _APPLY_DELAY_MS = m


# --- Backend management ---

def _choose_backend() -> RGBBackend:
    kind = str(os.environ.get("RGB_BACKEND", "hid")).strip().lower()
    if kind in ("hid", "direct", "direct_hid"):
        if DirectHIDBackend is not None:
            return DirectHIDBackend()  # type: ignore[no-any-return]
        return NoopBackend()
    # Fallback to no-op
    return NoopBackend()


def connect(wait_s: float = 5.0) -> bool:
    """Prepare backend and label map. No external programs required.
    - Uses Direct HID backend by default (RGB_BACKEND=hid).
    - Builds label->index map from data/maps/*_leds.json.
    """
    global _backend, km
    km = None
    _backend = _choose_backend()
    ok = _backend.connect()
    if not ok:
        raise RuntimeError("Failed to initialize RGB backend.")
    map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"
    km = RGBLabelController(json_path=str(map_path))
    # Clear local caches
    _LAST_LABEL_COLOR.clear()
    return True


def disconnect() -> None:
    global _backend, km
    try:
        if _backend is not None:
            _backend.disconnect()
    except Exception:
        pass
    _backend = None
    km = None
    _LAST_LABEL_COLOR.clear()


def is_connected() -> bool:
    return (_backend is not None and _backend.is_connected()) and (km is not None)


# --- Public LED helpers ---

def init_all_keys(debug: bool = False) -> bool:
    if _backend is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")
    # Approximate total by highest mapped index + 1
    try:
        total = max(km.label_to_index.values()) + 1 if km.label_to_index else 0
    except Exception:
        total = 0
    ok = _backend.init_all_keys(total_leds=total, debug=debug)
    try:
        time.sleep(0.05)
    except Exception:
        pass
    _LAST_LABEL_COLOR.clear()
    return ok


def get_key_color(label: str, fresh: bool = True) -> List[Tuple[int, int, int]]:
    if _backend is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")
    idx = km.label_to_index.get(str(label).lower())
    if idx is None:
        # Unknown label: return black
        return [(0, 0, 0)]
    try:
        c = _backend.get_color(idx, fresh=fresh)
        return [c]
    except Exception:
        return [(_LAST_LABEL_COLOR.get(str(label).lower(), (0, 0, 0)))]


def _to_color(c: RGBColor | Tuple[int, int, int]) -> RGBColor:
    if isinstance(c, RGBColor):
        return c
    try:
        r, g, b = c  # type: ignore[misc]
        return RGBColor(int(r), int(g), int(b))
    except Exception:
        return RGBColor(0, 0, 0)


def set_key_color(label: str, color: RGBColor | Tuple[int, int, int], debug: bool = False) -> bool:
    if _backend is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")
    idx = km.label_to_index.get(str(label).lower())
    if idx is None:
        return False
    col = _to_color(color)
    tgt = (int(col.red), int(col.green), int(col.blue))
    if _LAST_LABEL_COLOR.get(str(label).lower()) == tgt:
        return True
    ok = _backend.set_color(idx, col)
    try:
        time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
    except Exception:
        pass
    if ok:
        _LAST_LABEL_COLOR[str(label).lower()] = tgt
        if debug:
            try:
                print(f"[DEBUG] {str(label).upper()} -> {tgt}")
            except Exception:
                pass
    return ok


def set_labels_atomic(label_to_color: Dict[str, RGBColor | Tuple[int, int, int]]) -> bool:
    if _backend is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")
    # Debug toggle via env or API
    dbg = _ATOMIC_DEBUG or (str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes"))

    # Resolve changes and skip cached no-ops
    indices: List[int] = []
    colors: List[RGBColor] = []
    for lab, col_any in label_to_color.items():
        key = str(lab).lower()
        idx = km.label_to_index.get(key)
        if idx is None:
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] unknown label='{lab}'")
                except Exception:
                    pass
            continue
        col = _to_color(col_any)
        tgt = (int(col.red), int(col.green), int(col.blue))
        if _LAST_LABEL_COLOR.get(key) == tgt:
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] skip-noop idx={idx} label='{lab}'")
                except Exception:
                    pass
            continue
        indices.append(idx)
        colors.append(col)

    if not indices:
        if dbg:
            try:
                print("[RGB-ATOMIC] no-op (no changes)")
            except Exception:
                pass
        return True

    ok = _backend.set_many(indices, colors)
    if ok:
        try:
            time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
        except Exception:
            pass
        try:
            for lab, col_any in label_to_color.items():
                col = _to_color(col_any)
                _LAST_LABEL_COLOR[str(lab).lower()] = (int(col.red), int(col.green), int(col.blue))
        except Exception:
            pass
        if dbg:
            try:
                print(f"[RGB-ATOMIC] applied; changes={len(indices)}")
            except Exception:
                pass
        return True
    return False