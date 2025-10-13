from __future__ import annotations

"""
LED-bus handshake utilities

ëª©í‘œ:
- ?¤ë³´??LED 4??right_alt/right_fn/menu/right_ctrl)ë¥?ë©”ëª¨ë¦?IO ë²„ìŠ¤???œì–´? ìœ¼ë¡??¬ìš©.
- CPU??ë³€???‘ê·¼(get/set)??ë²„ìŠ¤ ?¬ì´?´ë¡œ ê°ì‹¸ê³? ACKë¥?LED?ì„œ ?½ì–´ ì§„í–‰/?€ê¸?ê²°ì •.
- ?´ë? ACK(?ê? ?‘ë‹µ)??? íƒ ê°€?¥í•˜?? ??ƒ LED ?½ê¸°/?°ê¸°ë¥??µí•´ ?íƒœë¥??ì •.

ë²„ìŠ¤ ?œì–´??ë§¤í•‘ (utils.keyboard_presets???•ì˜):
- BUS_ADDR_VALID: right_alt (ì£¼ì†Œ ? íš¨)
- BUS_RD:         right_fn  (?½ê¸° ?¤íŠ¸ë¡œë¸Œ)
- BUS_WR:         menu      (?°ê¸° ?¤íŠ¸ë¡œë¸Œ)
- BUS_ACK:        right_ctrl(?‘ë‹µ/?€ê¸?

ì£¼ì˜:
- ?˜ë“œ?¨ì–´ ?¸ì¶œ?€ rgb_controllerë¥??µí•´ ?˜í–‰. ê°€?¥í•˜ë©?set_labels_atomic?¼ë¡œ ?„ë ˆ???¨ìœ„ ?ìš©.
- ë³€????VARIABLE_KEYS)???œí•´ ?¸ë“œ?°ì´?¬ë? ?ìš©?˜ì—¬ ê³¼ë„??? ê???ë°©ì?.
"""

from typing import Dict, Tuple, Any
import time
from rgb_types import RGBColor
from rgb_controller import set_labels_atomic, set_key_color, get_key_color
from utils.keyboard_presets import (
    BINARY_COLORS,
    VARIABLE_KEYS,
    BUS_ADDR_VALID,
    BUS_RD,
    BUS_WR,
    BUS_ACK,
)


def _on_off(label: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    if label in BINARY_COLORS:
        return BINARY_COLORS[label]
    # default
    return (255, 255, 255), (0, 0, 0)


def _dist2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    dr, dg, db = a[0]-b[0], a[1]-b[1], a[2]-b[2]
    return dr*dr + dg*dg + db*db


def _read_bool(label: str) -> bool:
    on_rgb, off_rgb = _on_off(label)
    r, g, b = get_key_color(label, fresh=True)[0]
    cur = (int(r), int(g), int(b))
    return _dist2(cur, on_rgb) <= _dist2(cur, off_rgb)


class BusInterface:
    def __init__(self, *, ack_mode: str = "internal", ack_pulse_ms: int = 12,
                 settle_ms: int = 8, ack_timeout_ms: int = 200) -> None:
        """
        ack_mode: 'internal' | 'external' | 'auto'
          - internal: ì»¨íŠ¸ë¡¤ëŸ¬ê°€ ACK LEDë¥?ì§ì ‘ ?„ìŠ¤(?°ê¸°) ???ì‹ ???½ê³  ì§„í–‰
          - external: ?¸ë?(?¤ë¥¸ ?ì´?„íŠ¸)ê°€ ACKë¥?ì¼œì¤„ ?Œê¹Œì§€ ?€ê¸??½ê¸°ë§?
          - auto: ë¨¼ì? ?¸ë? ACK ?€ê¸? ?€?„ì•„?ƒì´ë©??´ë? ?„ìŠ¤
        ack_pulse_ms: ?´ë? ACK ?„ìŠ¤ ? ì? ?œê°„
        settle_ms: ?œì–´???‹ì—… ???•ì°© ?€ê¸?LED ?˜ë“œ?¨ì–´ ë°˜ì˜ ?€ê¸?
        ack_timeout_ms: ACK ?€ê¸??œí•œ
        """
        self.ack_mode = ack_mode
        self.ack_pulse_ms = max(1, int(ack_pulse_ms))
        self.settle_ms = max(0, int(settle_ms))
        self.ack_timeout_ms = max(1, int(ack_timeout_ms))

    # --- low-level helpers ---
    def _apply_signals(self, states: Dict[str, bool]) -> None:
        payload: Dict[str, RGBColor] = {}
        for lab, on in states.items():
            on_rgb, off_rgb = _on_off(lab)
            rgb = on_rgb if on else off_rgb
            payload[lab] = RGBColor(*rgb)
        ok = set_labels_atomic(payload)
        if not ok:
            # Fallback per-key (these calls include their own settle delay)
            for lab, col in payload.items():
                try:
                    set_key_color(lab, col)
                except Exception:
                    pass
        # Note: set_labels_atomic/set_key_color already include an apply delay;
        # avoid double-sleep here to reduce cycle latency safely.

    def _ack_on(self) -> None:
        on_rgb, _ = _on_off(BUS_ACK)
        try:
            set_key_color(BUS_ACK, RGBColor(*on_rgb))
        except Exception:
            pass

    def _ack_off(self) -> None:
        _, off_rgb = _on_off(BUS_ACK)
        try:
            set_key_color(BUS_ACK, RGBColor(*off_rgb))
        except Exception:
            pass

    def _wait_ack(self, timeout_ms: int | None = None) -> bool:
        limit = self.ack_timeout_ms if timeout_ms is None else max(1, int(timeout_ms))
        deadline = time.time() + (limit / 1000.0)
        while time.time() < deadline:
            if _read_bool(BUS_ACK):
                return True
            time.sleep(0.005)
        return False

    # --- public API ---
    def begin_read(self) -> None:
        # ADDR_VALID=ON, RD=ON, WR=OFF
        self._apply_signals({BUS_ADDR_VALID: True, BUS_RD: True, BUS_WR: False})

    def begin_write(self) -> None:
        # ADDR_VALID=ON, WR=ON, RD=OFF
        self._apply_signals({BUS_ADDR_VALID: True, BUS_RD: False, BUS_WR: True})

    def end_cycle(self) -> None:
        # All off (ACK???´ë? ?„ìŠ¤ ???Œê±°)
        self._apply_signals({BUS_ADDR_VALID: False, BUS_RD: False, BUS_WR: False})
        # ?¸ë? ACK ëª¨ë“œ?ì„œ???¬ì´??ì¢…ë£Œ ?œì ??ACKê°€ ì¼œì ¸ ?ˆìœ¼ë©??ì—° ?Œê±°ë¥?ê¸°ë‹¤ë¦????ˆìœ¼??        # ?¬ê¸°?œëŠ” ?´ë? ACKë§??Œê±°?œë‹¤.

    def handshake(self) -> bool:
        mode = (self.ack_mode or "internal").lower()
        if mode == "internal":
            self._ack_on()
            time.sleep(self.ack_pulse_ms / 1000.0)
            ok = _read_bool(BUS_ACK)
            self._ack_off()
            return ok
        elif mode == "external":
            return self._wait_ack()
        else:  # auto
            if self._wait_ack(int(self.ack_timeout_ms * 0.4)):
                return True
            # fallback to internal
            self._ack_on()
            time.sleep(self.ack_pulse_ms / 1000.0)
            ok = _read_bool(BUS_ACK)
            self._ack_off()
            return ok


class BusMemory:
    """ë©”ëª¨ë¦??˜í¼: ë³€?????‘ê·¼??ë²„ìŠ¤ ?¸ë“œ?°ì´?¬ë? ê°•ì œ?œë‹¤.

    - inner: DataMemoryRGBVisual(?ëŠ” ?¸í™˜) ?¸ìŠ¤?´ìŠ¤
    - bus:   BusInterface
    - only_variable_keys: Trueë©?VARIABLE_KEYS???´ë‹¹?˜ëŠ” ?´ë¦„?ë§Œ ?¸ë“œ?°ì´???ìš©
    """
    def __init__(self, inner: Any, bus: BusInterface, *, only_variable_keys: bool = True) -> None:
        self._inner = inner
        self._bus = bus
        self._only_vars = bool(only_variable_keys)
        # Optional sink for watch/break events (set by CPU)
        self._sink: Any | None = None

    # External modules (e.g., CPU) can register a sink to observe bus-level mem ops
    def set_sink(self, sink: Any) -> None:
        """Register an event sink object having on_bus_mem_event(dict) method."""
        self._sink = sink

    def _emit(self, direction: str, name: str, value: int | None = None) -> None:
        try:
            if self._sink is not None and hasattr(self._sink, "on_bus_mem_event"):
                ev = {"dir": direction, "name": str(name), "value": value}
                self._sink.on_bus_mem_event(ev)
        except Exception:
            pass

    def _is_mem_var(self, name: str) -> bool:
        if not self._only_vars:
            return True
        try:
            return str(name) in VARIABLE_KEYS
        except Exception:
            return False

    # ---- proxied API ----
    def get(self, name: str) -> int:
        if self._is_mem_var(name):
            t0 = time.time()
            self._bus.begin_read()
            try:
                ok = self._bus.handshake()
            finally:
                self._bus.end_cycle()
            lat_ms = int((time.time() - t0) * 1000.0)
            if not ok:
                # Promote to FAULT and stop via exception
                try:
                    from utils.control_plane import set_run_state
                    set_run_state("FAULT")
                except Exception:
                    pass
                try:
                    if self._sink is not None and hasattr(self._sink, "on_bus_mem_event"):
                        ev = {"dir": "READ", "name": str(name), "value": None, "lat_ms": lat_ms, "error": "ACK_FAIL"}
                        self._sink.on_bus_mem_event(ev)
                except Exception:
                    pass
                raise Exception("BUS_ACK_FAIL_READ")
            # ?¸ë“œ?°ì´??ê²°ê³¼?€ ë¬´ê??˜ê²Œ LEDê°€ ì§„ì‹¤ ?ŒìŠ¤ë¡??™ìž‘?˜ë?ë¡?ê°’ì„ ?½ëŠ”??
            # (?¸ë? ACK ?¬ìš© ?œì—??okê°€ ì§„í–‰ ì¡°ê±´ ?˜ë?ë¥?ê°–ëŠ”??
            val = self._inner.get(name)
            # Emit watch event after successful read with latency metadata
            try:
                if self._sink is not None and hasattr(self._sink, "on_bus_mem_event"):
                    ev = {"dir": "READ", "name": str(name), "value": val, "lat_ms": lat_ms}
                    self._sink.on_bus_mem_event(ev)
            except Exception:
                pass
            return val
        val = self._inner.get(name)
        return val

    def set(self, name: str, val: int) -> None:
        if self._is_mem_var(name):
            t0 = time.time()
            self._bus.begin_write()
            try:
                ok = self._bus.handshake()
            finally:
                self._bus.end_cycle()
            lat_ms = int((time.time() - t0) * 1000.0)
            if not ok:
                # Promote to FAULT and stop via exception
                try:
                    from utils.control_plane import set_run_state
                    set_run_state("FAULT")
                except Exception:
                    pass
                try:
                    if self._sink is not None and hasattr(self._sink, "on_bus_mem_event"):
                        ev = {"dir": "WRITE", "name": str(name), "value": val, "lat_ms": lat_ms, "error": "ACK_FAIL"}
                        self._sink.on_bus_mem_event(ev)
                except Exception:
                    pass
                raise Exception("BUS_ACK_FAIL_WRITE")
            self._inner.set(name, val)
            # Emit watch event after write with latency metadata
            try:
                if self._sink is not None and hasattr(self._sink, "on_bus_mem_event"):
                    ev = {"dir": "WRITE", "name": str(name), "value": val, "lat_ms": lat_ms}
                    self._sink.on_bus_mem_event(ev)
            except Exception:
                pass
            return
        self._inner.set(name, val)

    # Optional helpers used by CPU/DataMemoryRGBVisual
    def set_flag(self, label: str, on: bool) -> None:
        # ?Œëž˜ê·??…ë°?´íŠ¸?ëŠ” ë²„ìŠ¤ ê°•ì œ ?ìš©?˜ì? ?ŠìŒ (?œê° ? í˜¸)
        if hasattr(self._inner, "set_flag"):
            self._inner.set_flag(label, on)

    def get_flag(self, label: str) -> bool:
        if hasattr(self._inner, "get_flag"):
            return bool(self._inner.get_flag(label))
        return False

