import time
import time
import json
from typing import Dict, List, Optional, Tuple
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from config import MAPS_DIR
from utils.keyboard_map import RGBLabelController
from utils.keyboard_map import ALIASES as _ALIASES  # 진단/보강용

client: Optional[OpenRGBClient] = None
kb = None
km: Optional[RGBLabelController] = None

# Runtime debug toggle for atomic updates (default: False)
_ATOMIC_DEBUG: bool = False

def set_atomic_debug(on: bool) -> None:
    """Enable/disable verbose logs inside set_labels_atomic without env vars."""
    global _ATOMIC_DEBUG
    _ATOMIC_DEBUG = bool(on)

# --- 내부 유틸 ---

def _refresh_device_leds(dev=None):
    """장치의 최신 LED 상태를 갱신한다.
    - 인자로 장치 객체가 주어지면 해당 객체를 새로고침
    - 없으면 글로벌 kb를 새로고침
    """
    target = dev or kb
    try:
        if target is not None:
            target.refresh()
    except Exception:
        pass

def safe_set_direct_and_sync(kb):
    """제어 전 1회: 모드 전환 → 메타데이터 갱신 → 전체 올블랙 초기화"""
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
        raise RuntimeError("키보드 장치를 찾지 못했습니다.")

    kb = keyboards[0]
    safe_set_direct_and_sync(kb)

    map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"
    km = RGBLabelController(client, json_path=map_path)
    _ensure_stage_labels(km)
    try:
        stage_keys = ['up','down','left','right']
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
                'delete','end','page_down','insert','home','page_up','print_screen','scroll_lock','pause_break'
            ]
            mapping = {lab: km.label_to_index.get(lab, None) for lab in op_labels}
            print(f"[OP-BLOCK] label->index {mapping}")
    except Exception:
        pass
    
    return True

def _ensure_stage_labels(km: RGBLabelController) -> None:
    """방향키 라벨(up/down/left/right)이 누락된 경우 JSON을 직접 읽어 보강.
    - 일부 환경에서 별칭 매칭 누락 시 표시가 전혀 안 보일 수 있으므로 안전망 제공.
    """
    try:
        path = getattr(km, 'json_path', None)
        if not path:
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # name_raw 정확 일치로 탐색
        want = {
            'up': 'Key: Up Arrow',
            'down': 'Key: Down Arrow',
            'left': 'Key: Left Arrow',
            'right': 'Key: Right Arrow',
        }
        # 이미 존재하면 스킵
        exists = set(km.label_to_index.keys())
        for lab, raw in want.items():
            if lab in exists:
                continue
            idx = None
            for row in data.get('leds', []):
                if str(row.get('name_raw','')).strip().lower() == raw.lower():
                    idx = int(row['index'])
                    break
            if idx is not None:
                km.label_to_index[lab] = idx
    except Exception:
        # 보강 실패는 치명적이지 않음
        pass

def disconnect():
    global client
    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass
        finally:
            client = None

def init_all_keys(debug: bool = False) -> bool:
    """
    Clear all keyboard LEDs to black in a single atomic update.
    This avoids per-key mode switching that can cause flicker or
    unexpected colors on first initialization (e.g., after cold boot).
    """
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다.")

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
        time.sleep(0.02)
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
        raise RuntimeError("먼저 connect()를 호출해야 합니다.")
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
        raise RuntimeError("먼저 connect()를 호출해야 합니다.")

    prev = get_key_color(label, fresh=True)[0] if debug else None
    ok = km.set(label, color)
    time.sleep(0.02)  # 하드웨어 안정화 대기

    if ok and debug:
        after = (color.red, color.green, color.blue)
        print(f"[DEBUG] {label.upper()} {prev} -> {after}")
    return ok

def set_labels_atomic(label_to_color: Dict[str, RGBColor]) -> bool:
    """
    여러 라벨을 한 번에 적용(배치)하여 중간 프레임(두 키 on/모두 off)을 방지.
    stage 표시처럼 상호배타적 갱신에 적합. 지연(sleep) 없음.
    """
    if kb is None or km is None:
        raise RuntimeError("먼저 connect()를 호출해야 합니다.")

    # 현재 색 배열을 기반으로 덮어쓰기 후, 한 번에 set_colors 적용
    try:
        # km가 가리키는 실제 키보드 디바이스를 우선 사용(장치 불일치 방지)
        dev = None
        try:
            dev = km._load_keyboard()  # type: ignore[attr-defined]
        except Exception:
            dev = None
        device = dev or kb

        if device is None:
            return False

        # 항상 direct 모드 보장
        try:
            device.set_mode("direct")
        except Exception:
            pass

        try:
            _refresh_device_leds(device)
        except Exception:
            pass

        # colors 원본 확보
        colors: List[RGBColor] = [led.color for led in device.leds]

        # 상세 디버그 출력 토글 (환경변수 RGB_ATOMIC_DEBUG=1|true|yes|y)
        dbg = False
        try:
            import os
            dbg = str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes")
        except Exception:
            dbg = False
        # Runtime override (no env needed)
        try:
            if _ATOMIC_DEBUG:
                dbg = True
        except Exception:
            pass

        changes: List[Tuple[int, RGBColor]] = []
        for lab, col in label_to_color.items():
            key = lab.lower()
            idx = km.label_to_index.get(key)
            if idx is None or not (0 <= idx < len(colors)):
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] resolve-miss label='{lab}' -> idx=None (leds={len(colors)})")
                    except Exception:
                        pass
                continue
            colors[idx] = col
            changes.append((idx, col))
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] plan idx={idx} label='{lab}' color=({col.red},{col.green},{col.blue})")
                except Exception:
                    pass

        if not changes:
            try:
                print("[WARN] set_labels_atomic: no index resolved for:", list(label_to_color.keys()))
            except Exception:
                pass
            return False

        ok = False
        try:
            device.set_colors(colors)
            ok = True
        except Exception as ex:
            ok = False
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] device.set_colors failed: {ex}")
                except Exception:
                    pass

        # 안전 확보: 변경된 키는 개별로도 한 번 더 적용
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

        if ok or ok_any:
            time.sleep(0.02)
            if dbg:
                try:
                    mode = "batch" if ok else "per-key"
                    print(f"[RGB-ATOMIC] applied via {mode}; changes={len(changes)}")
                except Exception:
                    pass
            return True
        # Final fallback: use label-driven km.set for each entry
        applied = False
        for lab, col in label_to_color.items():
            try:
                if km.set(lab, col):
                    applied = True
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] fallback km.set ok label='{lab}'")
                        except Exception:
                            pass
            except Exception as ex2:
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] fallback km.set fail label='{lab}': {ex2}")
                    except Exception:
                        pass
        if applied:
            try:
                time.sleep(0.02)
            except Exception:
                pass
            return True
        if dbg:
            try:
                print("[RGB-ATOMIC] apply failed; no changes took effect")
            except Exception:
                pass
        return False
    except Exception as ex:
        try:
            import os
            if str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes"):
                print(f"[RGB-ATOMIC] exception: {ex}")
        except Exception:
            pass
        return False
