from __future__ import annotations

import os
import json
from typing import Iterable, Tuple, Dict, Optional, List

# hidapi 우선, 실패 시 pyhidapi 폴백
try:
    import hid  # type: ignore
except Exception:
    try:
        from pyhidapi import hid as hid  # type: ignore
    except Exception:  # pragma: no cover
        hid = None  # type: ignore

from rgb_types import RGBColor
from config import DATA_DIR


class DirectHIDBackend:
    """Windows-first HID backend for Corsair K70 RGB TKL (via hidapi/pyhidapi).

    - 외부 프로그램 없이 동작.
    - data/devices/corsair_k70_tkl_hid.json 설정을 읽어 전송.
    - 설정이 없거나 장치 열기 실패 시 캐시 모드로 동작.
    """

    VID_CORSAIR = 0x1B1C

    def __init__(self) -> None:
        self._devs: List[hid.device] = []  # type: ignore[name-defined]
        self._connected = False
        self._index_range: int = 0
        self._cache: Dict[int, Tuple[int, int, int]] = {}
        self._paths: List[bytes] = []
        self._cfg: Dict[str, object] = {}
        self._method: str = "feature"  # or "output"
        self._remap: List[int] = []
        self._filter_usage_page: Optional[int] = None
        self._filter_interfaces: Optional[List[int]] = None

    # --------- Device selection ---------
    def _pick_devices(self) -> List[bytes]:
        if hid is None:
            return []
        try:
            devices = hid.enumerate(self.VID_CORSAIR, 0)
        except Exception:
            devices = []
        paths: List[bytes] = []
        for d in devices:
            try:
                vid = int(d.get('vendor_id', 0))
                pid = int(d.get('product_id', 0))
                prod = (d.get('product_string') or '').lower()
                path = d.get('path')
                iface = d.get('interface_number')
                upage = d.get('usage_page')
            except Exception:
                continue
            if vid != self.VID_CORSAIR or path is None:
                continue
            # 설정 필터 적용
            if self._filter_usage_page is not None and int(upage) != int(self._filter_usage_page):
                continue
            if self._filter_interfaces is not None and (iface not in self._filter_interfaces):
                continue
            # 기본 선택 기준(없으면 전체)
            if (pid == 0x1B73) or ('k70' in prod and 'tkl' in prod):
                paths.append(path)
        # 중복 제거
        uniq: List[bytes] = []
        for p in paths:
            if p not in uniq:
                uniq.append(p)
        # 필터가 없고 paths가 비면 모든 경로 반환(최후 fallback)
        if not uniq:
            uniq = [d.get('path') for d in (devices or []) if d.get('path')]
        return uniq

    # --------- Config loading ---------
    def _config_path(self) -> str:
        env = os.environ.get("K70_TKL_HID_CONFIG", "").strip()
        if env:
            return env
        return str(DATA_DIR / "devices" / "corsair_k70_tkl_hid.json")

    def _parse_hex(self, s: str) -> bytes:
        parts = [p for p in s.replace("\n", " ").replace("\t", " ").split(" ") if p]
        arr: List[int] = []
        for p in parts:
            try:
                arr.append(int(p, 16))
            except Exception:
                pass
        return bytes(arr)

    def _load_config(self) -> None:
        path = self._config_path()
        self._cfg = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        self._cfg = cfg
        method = str(cfg.get('method', 'feature')).strip().lower()
        self._method = method if method in ('feature', 'output') else 'feature'
        remap = cfg.get('remap', [])
        try:
            self._remap = [int(x) for x in remap] if isinstance(remap, list) else []
        except Exception:
            self._remap = []
        # 필터 읽기
        try:
            filt = cfg.get('filter', {})
            if isinstance(filt, dict):
                up = filt.get('usage_page', None)
                if up is not None:
                    self._filter_usage_page = int(up)
                if isinstance(filt.get('interface_numbers'), list):
                    self._filter_interfaces = [int(i) for i in filt.get('interface_numbers')]
        except Exception:
            pass

    # --------- Lifecycle ---------
    def connect(self) -> bool:
        self._load_config()
        dbg = str(os.environ.get('HID_DEBUG', '')).strip().lower() in ('1', 'true')
        if hid is None:
            self._connected = True
            if dbg:
                print('[HID] hid module not available; cache-only mode')
            return True
        try:
            paths = self._pick_devices()
            if dbg:
                try:
                    devs = hid.enumerate(self.VID_CORSAIR, 0)
                    print('[HID] enumerate:', len(devs))
                except Exception as ex:
                    print('[HID] enumerate error:', ex)
                print('[HID] pick paths ->', len(paths))
            self._devs = []
            for p in paths:
                try:
                    d = hid.device()
                    d.open_path(p)
                    try:
                        d.set_nonblocking(True)
                    except Exception:
                        pass
                    self._devs.append(d)
                except Exception as ex:
                    if dbg:
                        print('[HID] open error:', ex)
            self._paths = paths
            self._connected = True
            if dbg:
                print('[HID] opened =', len(self._devs))
            self._send_init()
            return True
        except Exception as ex:
            if dbg:
                print('[HID] connect exception:', ex)
            self._devs = []
            self._connected = True
            return True

    def disconnect(self) -> None:
        try:
            for d in self._devs:
                try:
                    d.close()
                except Exception:
                    pass
        finally:
            self._devs = []
            self._connected = False
            self._cache.clear()

    def is_connected(self) -> bool:
        return bool(self._connected)

    # --------- Public API ---------
    def init_all_keys(self, total_leds: int, debug: bool = False) -> bool:
        self._index_range = max(0, int(total_leds))
        self._cache = {i: (0, 0, 0) for i in range(self._index_range)}
        self._send_frame_bulk()
        return True

    def set_color(self, index: int, color: RGBColor) -> bool:
        i = int(index)
        if i < 0:
            return False
        self._cache[i] = color.as_tuple()
        self._send_key_update(i, color)
        self._send_commit()
        return True

    def set_many(self, indices: Iterable[int], colors: Iterable[RGBColor]) -> bool:
        indices = list(indices)
        colors = list(colors)
        for i, c in zip(indices, colors):
            self._cache[int(i)] = c.as_tuple()

        # If bulk config exists, prefer a single bulk frame
        cfg_bulk = self._cfg.get('bulk') if isinstance(self._cfg, dict) else None
        if isinstance(cfg_bulk, dict):
            self._send_frame_bulk()
            return True

        # Fallback: batch per-key updates with a single commit
        for i, c in zip(indices, colors):
            self._send_key_update(int(i), c)
        
        self._send_commit()
        return True

    def get_color(self, index: int, fresh: bool = True) -> Tuple[int, int, int]:
        return self._cache.get(int(index), (0, 0, 0))

    # --------- Low-level USB helpers ---------
    def _hid_send(self, payload: bytes) -> None:
        if not self._devs or not payload:
            return
        dbg = str(os.environ.get('HID_DEBUG', '')).strip().lower() in ('1', 'true')
        send_both = str(os.environ.get('HID_SEND_BOTH', '')).strip().lower() in ('1', 'true')
        for dev in self._devs:
            try:
                if self._method == 'feature' or send_both:
                    if dbg:
                        print('[HID] feature send len=', len(payload))
                    dev.send_feature_report(payload)
                if self._method == 'output' or send_both:
                    if dbg:
                        print('[HID] output send len=', len(payload))
                    dev.write(payload)
            except Exception as ex:
                if dbg:
                    print('[HID] send error:', ex)
                continue

    def _send_init(self) -> None:
        cfg = self._cfg.get('init') if isinstance(self._cfg, dict) else None
        dbg = str(os.environ.get('HID_DEBUG', '')).strip().lower() in ('1', 'true')
        if not isinstance(cfg, list):
            if dbg:
                print('[HID] no init')
            return
        for item in cfg:
            try:
                hx = self._parse_hex(str(item))
                if dbg:
                    print('[HID] init ->', hx)
                self._hid_send(hx)
            except Exception as ex:
                if dbg:
                    print('[HID] init error:', ex)
                pass

    def _send_commit(self) -> None:
        cfg = self._cfg.get('commit') if isinstance(self._cfg, dict) else None
        dbg = str(os.environ.get('HID_DEBUG', '')).strip().lower() in ('1', 'true')

        # Legacy list-based format
        if isinstance(cfg, list):
            if dbg:
                print('[HID] commit (legacy list format)')
            for item in cfg:
                try:
                    hx = self._parse_hex(str(item))
                    if dbg:
                        print('[HID] commit ->', hx)
                    self._hid_send(hx)
                except Exception as ex:
                    if dbg:
                        print('[HID] commit error:', ex)
            return

        # New dict-based format from autoconfig
        if not isinstance(cfg, dict):
            if dbg:
                print('[HID] no commit config found')
            return
        
        if dbg:
            print('[HID] commit (dict format)')
        try:
            prologue = self._parse_hex(str(cfg.get('prologue', '')))
            if not prologue:
                return
            
            length = 64 # Assume 64-byte reports
            buf = bytearray(length)
            
            report_id = int(self._cfg.get('report_id', 0))

            offset = 0
            if report_id != 0:
                buf[0] = report_id & 0xFF
                offset = 1

            buf[offset:offset+len(prologue)] = prologue
            
            if dbg:
                print('[HID] commit ->', bytes(buf))
            self._hid_send(bytes(buf))
        except Exception as ex:
            if dbg:
                print('[HID] commit error:', ex)

    def _apply_remap(self, idx: int) -> int:
        if self._remap and 0 <= idx < len(self._remap):
            try:
                return int(self._remap[idx])
            except Exception:
                return idx
        return idx

    # --- Per-key update ---
    def _send_key_update(self, index: int, color: RGBColor) -> None:
        cfg = self._cfg.get('per_key') if isinstance(self._cfg, dict) else None
        if not isinstance(cfg, dict):
            return
        try:
            prologue = self._parse_hex(str(cfg.get('prologue', '')))
            body_len = int(cfg.get('body_len', 4))
            
            if not prologue:
                return

            length = 64 # Assume 64-byte reports
            buf = bytearray(length)

            report_id = int(self._cfg.get('report_id', 0))

            offset = 0
            if report_id != 0:
                buf[0] = report_id & 0xFF
                offset = 1

            buf[offset:offset+len(prologue)] = prologue
            offset += len(prologue)

            idx_val = self._apply_remap(int(index))
            r, g, b = int(color.red), int(color.green), int(color.blue)
            
            if offset + body_len <= length:
                buf[offset] = idx_val & 0xFF
                buf[offset+1] = r & 0xFF
                buf[offset+2] = g & 0xFF
                buf[offset+3] = b & 0xFF

            self._hid_send(bytes(buf))
            # DO NOT COMMIT HERE. The caller is responsible.
        except Exception:
            pass

    # --- Bulk frame update ---
    def _send_frame_bulk(self) -> None:
        cfg = self._cfg.get('bulk') if isinstance(self._cfg, dict) else None
        if not isinstance(cfg, dict):
            return
        try:
            rid = int(cfg.get('report_id', 0))
            length = int(cfg.get('length', 0))
            off0 = int(cfg.get('offset0', 0))
            stride = int(cfg.get('stride', 3))
            order = str(cfg.get('order', 'RGB')).upper()
            count = int(cfg.get('count', 0))
            if length <= 0 or count <= 0 or stride <= 0:
                return
            buf = bytearray(length)
            if length >= 1:
                buf[0] = rid & 0xFF
            for logical_idx in range(count):
                phys = self._apply_remap(logical_idx)
                r, g, b = self._cache.get(logical_idx, (0, 0, 0))
                vals: Dict[str, int] = {'R': r, 'G': g, 'B': b}
                base = off0 + (phys * stride)
                for j, ch in enumerate(order[:stride]):
                    pos = base + j
                    if 0 <= pos < length:
                        buf[pos] = int(vals.get(ch, 0)) & 0xFF
            self._hid_send(bytes(buf))
            self._send_commit()
        except Exception:
            pass
