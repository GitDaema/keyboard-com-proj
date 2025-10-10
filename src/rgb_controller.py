"""RGB controller helpers for OpenRGB-driven keyboard LED control.

This module centralizes connection management and safe, low-flicker LED updates.
"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import json
from typing import Dict, List, Optional, Tuple

from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

from config import MAPS_DIR
from utils.keyboard_map import RGBLabelController

client: Optional[OpenRGBClient] = None
kb = None
km: Optional[RGBLabelController] = None

# Runtime debug toggle for atomic updates (default: False)
_ATOMIC_DEBUG: bool = False
# Global apply delay (ms) used after batch/per-key LED updates to allow hardware to settle
# Default 20ms is conservative; can be tuned at runtime via set_apply_delay_ms()
_APPLY_DELAY_MS: int = 20

# Group-atomic writes toggle (for fast mode): when enabled, callers may
# batch-update register groups (SRC1/SRC2/RES) to visually latch together.
_GROUP_ATOMIC: bool = False

# Last-state cache to avoid redundant writes when a label already has the
# requested color. Keys are lower-cased label strings.
_LAST_LABEL_COLOR: Dict[str, Tuple[int, int, int]] = {}

# Explicit export list to avoid any confusion during `from rgb_controller import ...`
__all__ = [
    'connect', 'disconnect', 'is_connected',
    'get_key_color', 'set_key_color', 'set_labels_atomic',
    'init_all_keys', 'set_apply_delay_ms', 'set_atomic_debug', 'set_group_atomic', 'is_group_atomic'
]


def set_atomic_debug(on: bool) -> None:
    """Enable/disable verbose logs inside set_labels_atomic without env vars."""
    global _ATOMIC_DEBUG
    _ATOMIC_DEBUG = bool(on)


def set_group_atomic(on: bool) -> None:
    """Enable/disable group-atomic update hint used by ALU/register writers."""
    global _GROUP_ATOMIC
    _GROUP_ATOMIC = bool(on)


def is_group_atomic() -> bool:
    return bool(_GROUP_ATOMIC)


def set_apply_delay_ms(ms: int) -> None:
    """Set per-apply settle delay (in milliseconds) for LED updates.
    Clamped to a safe range to preserve stability.
    """
    global _APPLY_DELAY_MS
    try:
        m = int(ms)
    except Exception:
        return
    # Keep within a safe window (5ms..40ms)
    if m < 5:
        m = 5
    if m > 40:
        m = 40
    _APPLY_DELAY_MS = m


# --- 디바이스 동기화 유틸 ---

def _refresh_device_leds(dev=None):
    """장치에서 최신 LED 상태를 다시 읽습니다.
    - 명시적으로 장치 객체가 주어지면 그 장치를 갱신
    - 아니면 전역 `kb`를 갱신
    """
    target = dev or kb
    try:
        if target is not None:
            target.refresh()
    except Exception:
        pass


def safe_set_direct_and_sync(kb):
    """안전하게 direct 모드로 전환 후 전체 LED를 블랙으로 초기화."""
    try:
        kb.set_mode("direct")
    except Exception:
        pass
    time.sleep(0.15)

    _refresh_device_leds(kb)

    try:
        kb.set_colors([RGBColor(0, 0, 0)] * len(kb.leds))
    except Exception:
        pass
    time.sleep(0.05)


# --- 공개 API ---

def connect():
    global client, kb, km
    client = OpenRGBClient(address="127.0.0.1", port=6742, name="K70Demo")

    devices = getattr(client, "devices", None) or client.get_devices()
    keyboards = [d for d in devices if getattr(d.type, "name", str(d.type)).lower() == "keyboard"]
    if not keyboards:
        raise RuntimeError("키보드 장치를 찾지 못했습니다")

    kb = keyboards[0]
    safe_set_direct_and_sync(kb)

    map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"
    km = RGBLabelController(client, json_path=map_path)
    try:
        stage_keys = ['up', 'down', 'left', 'right']
        missing = [k for k in stage_keys if k not in km.label_to_index]
        if missing:
            print(f"[WARN] Stage labels missing in map: {missing}")
        else:
            print("[INFO] Stage labels mapped:", {k: km.label_to_index[k] for k in stage_keys})
    except Exception:
        pass

    # Optional: dump 3x3 operator block mapping for debugging
    try:
        import os
        dbg = str(os.environ.get("OP_BLOCK_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes")
        dbg = dbg or (str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes"))
        if dbg:
            op_labels = [
                'delete', 'end', 'page_down', 'insert', 'home', 'page_up', 'print_screen', 'scroll_lock', 'pause_break'
            ]
            mapping = {lab: km.label_to_index.get(lab, None) for lab in op_labels}
            print(f"[OP-BLOCK] label->index {mapping}")
    except Exception:
        pass

    # 연결 시 마지막 상태 캐시 초기화(외부 변경으로 인한 stale 회피)
    try:
        _LAST_LABEL_COLOR.clear()
    except Exception:
        pass
    return True


def disconnect():
    global client
    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass
        finally:
            client = None
    # Ensure state cleared
    try:
        global kb, km
        kb = None
        km = None
    except Exception:
        pass
    # 연결 해제 시에도 마지막 상태 캐시 초기화
    try:
        _LAST_LABEL_COLOR.clear()
    except Exception:
        pass


def is_connected() -> bool:
    """현재 OpenRGB와 연결되어 있고 키보드/라벨 맵이 준비되었는지 여부."""
    return (client is not None) and (kb is not None) and (km is not None)


def init_all_keys(debug: bool = False) -> bool:
    """Clear all keyboard LEDs to black in a single atomic update.

    Avoids per-key mode switching that can cause flicker or unexpected colors
    on first initialization (e.g., after cold boot).
    """
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다")

    # Resolve the active keyboard device used by the label map
    device = None
    try:
        device = km._load_keyboard()  # type: ignore[attr-defined]
    except Exception:
        device = None
    device = device or kb

    # Ensure direct mode once (do not repeatedly flip mode per key)
    try:
        device.set_mode("direct")
    except Exception:
        pass

    # Refresh then apply an all-black frame in one shot
    try:
        _refresh_device_leds(device)
    except Exception:
        pass

    try:
        colors = [RGBColor(0, 0, 0)] * len(device.leds)
        device.set_colors(colors)
        time.sleep(0.05)
        # Redundant second pass helps on first run after cold boot
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
        # Fallback (best-effort): do nothing rather than per-key flicker
        return False


def get_key_color(label: str, fresh: bool = True) -> List[Tuple[int, int, int]]:
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다")
    if fresh:
        _refresh_device_leds()

    idx = km.label_to_index.get(label.lower())
    if idx is None:
        raise KeyError(f"'{label}' 라벨에 해당하는 LED를 찾을 수 없습니다.")

    result = []
    try:
        c = kb.leds[idx].color
    except Exception:
        c = kb.colors[idx]
    result.append((c.red, c.green, c.blue))
    return result


def set_key_color(label: str, color: RGBColor, debug: bool = False) -> bool:
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다")

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
    """Batch-apply multiple labels with minimal flicker and safe settle.
    Optimized for fast mode while preserving stability.
    """
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다")

    try:
        dev = None
        try:
            dev = km._load_keyboard()  # type: ignore[attr-defined]
        except Exception:
            dev = None
        device = dev or kb
        if device is None:
            return False

        try:
            device.set_mode("direct")
        except Exception:
            pass

        # Debug toggle
        dbg = False
        try:
            import os
            dbg = str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes")
        except Exception:
            dbg = False
        if _ATOMIC_DEBUG:
            dbg = True

        # Resolve changes first; skip no-ops via last-state cache
        changes: List[Tuple[int, RGBColor]] = []
        for lab, col in label_to_color.items():
            key = lab.lower()
            idx = km.label_to_index.get(key)
            if idx is None:
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] resolve-miss label='{lab}' -> idx=None")
                    except Exception:
                        pass
                continue
            try:
                tgt = (int(col.red), int(col.green), int(col.blue))
                if _LAST_LABEL_COLOR.get(key) == tgt:
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] skip-noop idx={idx} label='{lab}'")
                        except Exception:
                            pass
                    continue
            except Exception:
                pass
            changes.append((idx, col))

        if not changes:
            if dbg:
                try:
                    print("[RGB-ATOMIC] no-op (no changes)")
                except Exception:
                    pass
            return True

        # For small change sets, prefer per-key to avoid frame overhead
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
            # Build base colors without device refresh (prefer device.colors)
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
                # Fallback to per-key when batch fails
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
            # Update last-state cache
            try:
                for lab, col in label_to_color.items():
                    _LAST_LABEL_COLOR[lab.lower()] = (int(col.red), int(col.green), int(col.blue))
            except Exception:
                pass
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] applied; changes={len(changes)} (mode={'per-key' if len(changes)<=SMALL_N else 'batch'})")
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
