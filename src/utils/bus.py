from __future__ import annotations

"""
LED-bus handshake utilities

목표:
- ?�보??LED 4??right_alt/right_fn/menu/right_ctrl)�?메모�?IO 버스???�어?�으�??�용.
- CPU??변???�근(get/set)??버스 ?�이?�로 감싸�? ACK�?LED?�서 ?�어 진행/?��?결정.
- ?��? ACK(?��? ?�답)???�택 가?�하?? ??�� LED ?�기/?�기�??�해 ?�태�??�정.

버스 ?�어??매핑 (utils.keyboard_presets???�의):
- BUS_ADDR_VALID: right_alt (주소 ?�효)
- BUS_RD:         right_fn  (?�기 ?�트로브)
- BUS_WR:         menu      (?�기 ?�트로브)
- BUS_ACK:        right_ctrl(?�답/?��?

주의:
- ?�드?�어 ?�출?� rgb_controller�??�해 ?�행. 가?�하�?set_labels_atomic?�로 ?�레???�위 ?�용.
- 변????VARIABLE_KEYS)???�해 ?�드?�이?��? ?�용?�여 과도???��???방�?.
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
          - internal: 컨트롤러가 ACK LED�?직접 ?�스(?�기) ???�신???�고 진행
          - external: ?��?(?�른 ?�이?�트)가 ACK�?켜줄 ?�까지 ?��??�기�?
          - auto: 먼�? ?��? ACK ?��? ?�?�아?�이�??��? ?�스
        ack_pulse_ms: ?��? ACK ?�스 ?��? ?�간
        settle_ms: ?�어???�업 ???�착 ?��?LED ?�드?�어 반영 ?��?
        ack_timeout_ms: ACK ?��??�한
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
        # All off (ACK???��? ?�스 ???�거)
        self._apply_signals({BUS_ADDR_VALID: False, BUS_RD: False, BUS_WR: False})
        # ?��? ACK 모드?�서???�이??종료 ?�점??ACK가 켜져 ?�으�??�연 ?�거�?기다�????�으??        # ?�기?�는 ?��? ACK�??�거?�다.

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
    """메모�??�퍼: 변?????�근??버스 ?�드?�이?��? 강제?�다.

    - inner: DataMemoryRGBVisual(?�는 ?�환) ?�스?�스
    - bus:   BusInterface
    - only_variable_keys: True�?VARIABLE_KEYS???�당?�는 ?�름?�만 ?�드?�이???�용
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
            # ?�드?�이??결과?� 무�??�게 LED가 진실 ?�스�??�작?��?�?값을 ?�는??
            # (?��? ACK ?�용 ?�에??ok가 진행 조건 ?��?�?갖는??
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
        # ?�래�??�데?�트?�는 버스 강제 ?�용?��? ?�음 (?�각 ?�호)
        if hasattr(self._inner, "set_flag"):
            self._inner.set_flag(label, on)

    def get_flag(self, label: str) -> bool:
        if hasattr(self._inner, "get_flag"):
            return bool(self._inner.get_flag(label))
        return False

