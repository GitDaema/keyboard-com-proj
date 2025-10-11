"""RGB controller helpers for OpenRGB-driven keyboard LED control.

Centralizes connection management and low‑flicker LED updates.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

from config import MAPS_DIR
from utils.keyboard_map import RGBLabelController

client: Optional[OpenRGBClient] = None
kb = None
km: Optional[RGBLabelController] = None

# Runtime toggles
_ATOMIC_DEBUG: bool = False
_APPLY_DELAY_MS: int = 20  # settle after updates (ms)
_GROUP_ATOMIC: bool = False

# Cache to skip no‑op writes (label -> (r,g,b))
_LAST_LABEL_COLOR: Dict[str, Tuple[int, int, int]] = {}

__all__ = [
    'connect', 'disconnect', 'is_connected',
    'get_key_color', 'set_key_color', 'set_labels_atomic',
    'init_all_keys', 'set_apply_delay_ms', 'set_atomic_debug',
    'set_group_atomic', 'is_group_atomic'
]


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


def _refresh_device_leds(dev=None) -> None:
    target = dev or kb
    try:
        if target is not None:
            target.refresh()
    except Exception:
        pass


def safe_set_direct_and_sync(dev) -> None:
    try:
        dev.set_mode("direct")
    except Exception:
        pass
    time.sleep(0.15)
    _refresh_device_leds(dev)
    try:
        dev.set_colors([RGBColor(0, 0, 0)] * len(dev.leds))
    except Exception:
        pass
    time.sleep(0.05)


def connect(wait_s: float = 10.0) -> bool:
    """Connect to OpenRGB SDK server and prepare label mapping.

    Polls up to `wait_s` seconds for a keyboard device to appear.
    """
    global client, kb, km
    client = OpenRGBClient(address="127.0.0.1", port=6742, name="K70Demo")

    # Small grace period after server start
    try:
        time.sleep(0.6)
    except Exception:
        pass

    # Poll for keyboard device enumeration
    keyboards = []
    deadline = time.perf_counter() + max(0.0, float(wait_s))
    while time.perf_counter() < deadline:
        try:
            devices = getattr(client, "devices", None) or client.get_devices()
            keyboards = [
                d for d in (devices or [])
                if str(getattr(d.type, "name", str(d.type))).lower() == "keyboard"
            ]
            if keyboards:
                break
        except Exception:
            pass
        time.sleep(0.25)

    if not keyboards:
        raise RuntimeError(
            "Keyboard device not found. Ensure OpenRGB SDK server is running "
            "and that a keyboard is detected in OpenRGB UI."
        )

    kb_device = keyboards[0]
    safe_set_direct_and_sync(kb_device)

    map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"
    km = RGBLabelController(client, json_path=map_path)

    # Bind active device
    global kb
    kb = kb_device

    # Clear state cache on (re)connect
    try:
        _LAST_LABEL_COLOR.clear()
    except Exception:
        pass
    return True


def disconnect() -> None:
    global client, kb, km
    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass
        finally:
            client = None
    kb = None
    km = None
    try:
        _LAST_LABEL_COLOR.clear()
    except Exception:
        pass


def is_connected() -> bool:
    return (client is not None) and (kb is not None) and (km is not None)


def init_all_keys(debug: bool = False) -> bool:
    if kb is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")

    device = None
    try:
        device = km._load_keyboard()  # type: ignore[attr-defined]
    except Exception:
        device = None
    device = device or kb

    try:
        device.set_mode("direct")
    except Exception:
        pass

    try:
        _refresh_device_leds(device)
    except Exception:
        pass

    try:
        colors = [RGBColor(0, 0, 0)] * len(device.leds)
        device.set_colors(colors)
        time.sleep(0.05)
        device.set_colors(colors)
        try:
            time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
        except Exception:
            pass
        if debug:
            try:
                print(f"[INFO] Cleared {len(colors)} LEDs to black (atomic)")
            except Exception:
                pass
        return True
    except Exception:
        return False


def get_key_color(label: str, fresh: bool = True) -> List[Tuple[int, int, int]]:
    if kb is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")
    if fresh:
        _refresh_device_leds()

    idx = km.label_to_index.get(label.lower())
    if idx is None:
        raise KeyError(f"Unknown label '{label}'.")

    try:
        c = kb.leds[idx].color
    except Exception:
        c = kb.colors[idx]
    return [(c.red, c.green, c.blue)]


def set_key_color(label: str, color: RGBColor, debug: bool = False) -> bool:
    if kb is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")

    prev = get_key_color(label, fresh=True)[0] if debug else None
    ok = km.set(label, color)
    try:
        time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
    except Exception:
        pass

    if ok and debug:
        after = (color.red, color.green, color.blue)
        print(f"[DEBUG] {label.upper()} {prev} -> {after}")
    return ok


def set_labels_atomic(label_to_color: Dict[str, RGBColor]) -> bool:
    if kb is None or km is None:
        raise RuntimeError("connect() must be called before using LED functions.")

    try:
        device = None
        try:
            device = km._load_keyboard()  # type: ignore[attr-defined]
        except Exception:
            device = None
        device = device or kb
        if device is None:
            return False

        try:
            device.set_mode("direct")
        except Exception:
            pass

        # Debug toggle via env or API
        dbg = _ATOMIC_DEBUG
        if not dbg:
            try:
                import os
                dbg = str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes")
            except Exception:
                dbg = False

        # Resolve changes and skip cached no‑ops
        changes: List[Tuple[int, RGBColor]] = []
        for lab, col in label_to_color.items():
            key = str(lab).lower()
            idx = km.label_to_index.get(key)
            if idx is None:
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] unknown label='{lab}'")
                    except Exception:
                        pass
                continue
            tgt = (int(col.red), int(col.green), int(col.blue))
            if _LAST_LABEL_COLOR.get(key) == tgt:
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] skip-noop idx={idx} label='{lab}'")
                    except Exception:
                        pass
                continue
            changes.append((idx, col))

        if not changes:
            if dbg:
                try:
                    print("[RGB-ATOMIC] no-op (no changes)")
                except Exception:
                    pass
            return True

        SMALL_N = 5
        ok = False
        if len(changes) <= SMALL_N:
            ok_any = False
            for idx, col in changes:
                try:
                    device.leds[idx].set_color(col)
                    ok_any = True
                except Exception as ex:
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] per-key set fail idx={idx}: {ex}")
                        except Exception:
                            pass
            ok = ok_any
        else:
            try:
                colors: List[RGBColor] = list(getattr(device, "colors", []))
            except Exception:
                colors = []
            if not colors:
                try:
                    colors = [led.color for led in device.leds]
                except Exception:
                    colors = []
            try:
                for idx, col in changes:
                    if 0 <= idx < len(colors):
                        colors[idx] = col
                device.set_colors(colors)
                ok = True
            except Exception as ex:
                ok = False
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] device.set_colors failed: {ex}")
                    except Exception:
                        pass
                ok_any = False
                for idx, col in changes:
                    try:
                        device.leds[idx].set_color(col)
                        ok_any = True
                    except Exception as ex2:
                        if dbg:
                            try:
                                print(f"[RGB-ATOMIC] per-key fallback fail idx={idx}: {ex2}")
                            except Exception:
                                pass
                ok = ok_any

        if ok:
            try:
                time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
            except Exception:
                pass
            try:
                for lab, col in label_to_color.items():
                    _LAST_LABEL_COLOR[str(lab).lower()] = (int(col.red), int(col.green), int(col.blue))
            except Exception:
                pass
            if dbg:
                try:
                    mode = 'per-key' if len(changes) <= SMALL_N else 'batch'
                    print(f"[RGB-ATOMIC] applied; changes={len(changes)} mode={mode}")
                except Exception:
                    pass
            return True
        return False
    except Exception as ex:
        try:
            import os
            if str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes"):
                print(f"[RGB-ATOMIC] exception: {ex}")
        except Exception:
            pass
        return False

