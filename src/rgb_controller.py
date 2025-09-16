import time
from typing import List, Optional, Tuple
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from config import MAPS_DIR
from utils.keyboard_map import RGBLabelController

client: Optional[OpenRGBClient] = None
kb = None
km: Optional[RGBLabelController] = None

# --- 내부 유틸 ---

def _refresh_device_leds():
    """장치의 최신 LED 상태를 갱신한다."""
    try:
        kb.refresh()
    except Exception:
        pass

def safe_set_direct_and_sync(kb):
    """제어 전 1회: 모드 전환 → 메타데이터 갱신 → 전체 올블랙 초기화"""
    try:
        kb.set_mode("direct")
    except Exception:
        pass
    time.sleep(0.15)

    _refresh_device_leds()

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

    if ok and debug:
        after = (color.red, color.green, color.blue)
        print(f"[DEBUG] {label.upper()} {prev} -> {after}")
    return ok