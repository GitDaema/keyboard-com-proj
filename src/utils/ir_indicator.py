from typing import Dict, Tuple, Any, List
from openrgb.utils import RGBColor
from rgb_controller import set_labels_atomic, set_key_color, get_key_color
import time
from utils.keyboard_presets import (
    IR12, IR_OP_1BIT, IR_DST_1BIT, IR_ARG_2BIT,
    IR_ONOFF, IR_4STATE, VAR_TO_ID,
)
from sim.parser import parse_line  # for high-level source interpretation


def _clamp8(x: int) -> int:
    return int(x) & 0xFF


def _pair_colors(role: str, val2: int) -> RGBColor:
    # Fallback palette ensures availability for 'ARG' role
    palette = IR_4STATE.get(role) or IR_4STATE.get("OP") or [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)
    ]
    v = int(val2) & 0x03
    r, g, b = palette[v]
    return RGBColor(r, g, b)


def _bit_color(role: str, bit: int) -> RGBColor:
    on, off = IR_ONOFF[role]
    r, g, b = (on if int(bit) else off)
    return RGBColor(r, g, b)


def set_ir(op_nibble: int, dst_nibble: int, arg_byte: int) -> None:
    """IR 12키에 16비트(2바이트)를 혼합 모드로 표시.
    - F1,F2: OP[3:2], OP[1:0] (2비트/키)
    - F3,F4: DST[3:2], DST[1:0] (2비트/키)
    - F5~F12: ARG[7]..ARG[0] (1비트/키)
    """
    opn = int(op_nibble) & 0xF
    dst = int(dst_nibble) & 0xF
    arg = _clamp8(arg_byte)

    # Unified scheme: override legacy mapping with binary OP/DST and 4-state ARG
    payload: Dict[str, RGBColor] = {}

    # OP bits (MSB..LSB) -> F1..F4
    for i, lab in enumerate(IR_OP_1BIT):
        bit = (opn >> (3 - i)) & 1
        payload[lab] = _bit_color("OP", bit)

    # DST bits (MSB..LSB) -> F5..F8
    for i, lab in enumerate(IR_DST_1BIT):
        bit = (dst >> (3 - i)) & 1
        payload[lab] = _bit_color("DST", bit)

    # ARG pairs -> F9..F12 with 4-state colors
    for i, lab in enumerate(IR_ARG_2BIT):
        val2 = (arg >> (6 - 2*i)) & 0x3
        payload[lab] = _pair_colors("ARG", val2)

    ok = set_labels_atomic(payload)
    if not ok:
        for k, c in payload.items():
            try:
                set_key_color(k, c)
            except Exception:
                pass
    return

    payload: Dict[str, RGBColor] = {}

    # OP nibble → two 2-bit keys
    op_hi2 = (opn >> 2) & 0x3
    op_lo2 = opn & 0x3
    payload[IR_OP_2BIT[0]] = _pair_colors("OP", op_hi2)
    payload[IR_OP_2BIT[1]] = _pair_colors("OP", op_lo2)

    # DST nibble → two 2-bit keys
    dst_hi2 = (dst >> 2) & 0x3
    dst_lo2 = dst & 0x3
    payload[IR_DST_2BIT[0]] = _pair_colors("DST", dst_hi2)
    payload[IR_DST_2BIT[1]] = _pair_colors("DST", dst_lo2)

    # ARG byte bits → eight 1-bit keys (b7..b0)
    for i, lab in enumerate(IR_ARG_1BIT):
        bit = (arg >> (7 - i)) & 1  # F5=b7 ... F12=b0
        payload[lab] = _bit_color("ARG", bit)

    ok = set_labels_atomic(payload)
    if not ok:
        # Fallback: set individually
        for k, c in payload.items():
            try:
                set_key_color(k, c)
            except Exception:
                pass


_OPCODES: Dict[str, int] = {
    # Core
    "NOP": 0x0, "HALT": 0x1,
    "MOV": 0x2, "MOVI": 0x3,
    "ADD": 0x4, "ADDI": 0x5, "ADD8": 0x4,
    "SUB": 0x6, "SUBI": 0x7, "SUB8": 0x6,
    "AND": 0x8, "OR": 0x9, "XOR": 0xA,
    "SHL": 0xB, "SHR": 0xC,
    "CMP": 0xD, "CMPI": 0xD,
    "JMP": 0xE,
    # Branch conds share opcode; cond enc in DST nibble
    "BEQ": 0xF, "BNE": 0xF, "BMI": 0xF, "BPL": 0xF, "BVS": 0xF, "BVC": 0xF, "BCS": 0xF, "BCC": 0xF,
    # Misc map to NOP-like
    "PRINT": 0x0, "PRINT_RES": 0x0, "CLEARBITS": 0x0, "COPYBITS": 0x0,
    "LOADI8_BITS": 0x0, "UNPACK": 0x2, "UNPACK1": 0x2, "UNPACK2": 0x2, "PACK": 0x2,
}

_BR_COND: Dict[str, int] = {
    "BEQ": 0x0, "BNE": 0x1, "BPL": 0x2, "BMI": 0x3,
    "BVC": 0x4, "BVS": 0x5, "BCC": 0x6, "BCS": 0x7,
}


def _var_id(name: Any) -> int:
    try:
        s = str(name).strip().lower()
        return int(VAR_TO_ID.get(s, 0)) & 0xF
    except Exception:
        return 0


def encode_from_decoded(decoded: Tuple[str, tuple[Any, ...]]) -> Tuple[int, int, int]:
    """(op,args) → (op4, dst4, arg8) 근사 인코딩만 계산해서 반환."""
    op, args = decoded
    op_u = str(op).upper()
    op4 = int(_OPCODES.get(op_u, 0)) & 0xF
    dst4 = 0
    arg8 = 0
    if op_u in ("ADDI", "SUBI", "CMPI"):
        try:
            dst4 = _var_id(args[0])
            arg8 = _clamp8(int(args[1]))
        except Exception:
            dst4 = 0
            arg8 = 0
    elif op_u in ("ADD", "SUB", "AND", "OR", "XOR", "CMP"):
        try:
            dst4 = _var_id(args[0])
            arg8 = _var_id(args[1])
        except Exception:
            dst4 = 0
            arg8 = 0
    elif op_u in ("MOV", "SHL", "SHR"):
        try:
            dst4 = _var_id(args[0])
        except Exception:
            dst4 = 0
        if op_u == "MOV":
            # For MOV, also encode source var ID into ARG for display
            try:
                arg8 = _var_id(args[1])
            except Exception:
                arg8 = 0
        else:
            arg8 = 0
    elif op_u in ("MOVI",):
        try:
            dst4 = _var_id(args[0])
            arg8 = _clamp8(int(args[1]))
        except Exception:
            dst4 = 0
            arg8 = 0
    elif op_u in _BR_COND:
        dst4 = 0
        arg8 = ((int(_BR_COND[op_u]) & 0x3) << 6) & 0xFF
    else:
        dst4 = 0
        arg8 = 0
    return op4, dst4, arg8


def update_from_decoded(decoded: Tuple[str, tuple[Any, ...]]) -> None:
    op4, dst4, arg8 = encode_from_decoded(decoded)
    set_ir(op4, dst4, arg8)


def clear_ir() -> None:
    # Clear OP/DST bits to OFF and ARG pairs to black
    try:
        off_op = IR_ONOFF.get("OP", ((255,255,255),(0,0,0)))[1]
        off_dst = IR_ONOFF.get("DST", ((255,255,255),(0,0,0)))[1]
    except Exception:
        off_op = (0,0,0)
        off_dst = (0,0,0)
    for lab in IR_OP_1BIT:
        try:
            set_key_color(lab, RGBColor(*off_op))
        except Exception:
            pass
    for lab in IR_DST_1BIT:
        try:
            set_key_color(lab, RGBColor(*off_dst))
        except Exception:
            pass
    for lab in IR_ARG_2BIT:
        try:
            set_key_color(lab, RGBColor(0,0,0))
        except Exception:
            pass


# ------------ Calibration storage (optional) ------------
_CAL_OP_ONOFF: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = {}
_CAL_DST_ONOFF: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = {}
_CAL_ARG_4STATE: Dict[str, List[Tuple[int, int, int]]] = {}


def calibrate_ir(samples: int = 3, settle_ms: int = 10, debug: bool = False) -> None:
    """Calibrate IR colors per key for robust decoding.
    - Measures per-key ON/OFF for OP/DST and four-state colors for ARG pairs.
    - Stores centroids in module-level dicts used by read_ir(use_calibration=True).
    - Non-destructive: only affects decoding; can be re-run anytime.
    """
    def _avg_rgb(labels: List[str]) -> Dict[str, Tuple[int, int, int]]:
        d: Dict[str, Tuple[int, int, int]] = {}
        for lab in labels:
            rs = gs = bs = 0
            for _ in range(max(1, samples)):
                r, g, b = get_key_color(lab, fresh=True)[0]
                rs += int(r); gs += int(g); bs += int(b)
                if settle_ms > 0:
                    time.sleep(settle_ms / 1000.0)
            n = max(1, samples)
            d[lab] = (rs // n, gs // n, bs // n)
        return d

    # OP bits: measure OFF then ON per bit
    global _CAL_OP_ONOFF, _CAL_DST_ONOFF, _CAL_ARG_4STATE
    _CAL_OP_ONOFF = {}
    _CAL_DST_ONOFF = {}
    _CAL_ARG_4STATE = {}

    # OP OFF
    set_ir(0, 0, 0)
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)
    op_off = _avg_rgb(IR_OP_1BIT)
    # OP ON per bit
    for i, lab in enumerate(IR_OP_1BIT):
        opn = (1 << (3 - i)) & 0xF
        set_ir(opn, 0, 0)
        if settle_ms > 0:
            time.sleep(settle_ms / 1000.0)
        meas = _avg_rgb([lab])
        _CAL_OP_ONOFF[lab] = (meas[lab], op_off[lab]) if debug and False else (meas[lab], op_off[lab])
        # Normalize order: (on, off)
        _CAL_OP_ONOFF[lab] = (meas[lab], op_off[lab])

    # DST OFF
    set_ir(0, 0, 0)
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)
    dst_off = _avg_rgb(IR_DST_1BIT)
    # DST ON per bit
    for i, lab in enumerate(IR_DST_1BIT):
        dst = (1 << (3 - i)) & 0xF
        set_ir(0, dst, 0)
        if settle_ms > 0:
            time.sleep(settle_ms / 1000.0)
        meas = _avg_rgb([lab])
        _CAL_DST_ONOFF[lab] = (meas[lab], dst_off[lab])

    # ARG 4 states per pair
    for i, lab in enumerate(IR_ARG_2BIT):
        states: List[Tuple[int, int, int]] = []
        for val2 in range(4):
            arg = (val2 & 0x3) << (6 - 2 * i)
            set_ir(0, 0, arg)
            if settle_ms > 0:
                time.sleep(settle_ms / 1000.0)
            meas = _avg_rgb([lab])
            states.append(meas[lab])
        _CAL_ARG_4STATE[lab] = states

    if debug:
        print("[IR CAL] OP on/off:")
        for lab, (on, off) in _CAL_OP_ONOFF.items():
            print(f"  {lab}: on={on} off={off}")
        print("[IR CAL] DST on/off:")
        for lab, (on, off) in _CAL_DST_ONOFF.items():
            print(f"  {lab}: on={on} off={off}")
        print("[IR CAL] ARG 4-state:")
        for lab, arr in _CAL_ARG_4STATE.items():
            print(f"  {lab}: {arr}")


# ------------ New: Read IR back from keyboard (decode F1~F12) ------------
def _nearest_1bit(role: str, rgb: Tuple[int, int, int], lab: str | None = None) -> int:
    on, off = IR_ONOFF[role]
    def d2(a, b):
        return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2
    # Use calibration if available
    if lab is not None:
        if role == "OP" and lab in _CAL_OP_ONOFF:
            on, off = _CAL_OP_ONOFF[lab]
        if role == "DST" and lab in _CAL_DST_ONOFF:
            on, off = _CAL_DST_ONOFF[lab]
    return 1 if d2(rgb, on) < d2(rgb, off) else 0


def _nearest_2bit(role: str, rgb: Tuple[int, int, int], lab: str | None = None) -> int:
    palette = IR_4STATE.get(role) or IR_4STATE.get("OP") or [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)
    ]
    # Use calibration if available for ARG pairs
    if role == "ARG" and lab is not None and lab in _CAL_ARG_4STATE:
        palette = _CAL_ARG_4STATE[lab]
    def d2(a, b):
        return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2
    best = 0
    best_d = 10**12
    for i, col in enumerate(palette):
        dist = d2(rgb, col)
        if dist < best_d:
            best_d = dist
            best = i
    return best & 0x3


def read_ir(*, samples: int = 1, use_calibration: bool = True, debug: bool = False) -> Tuple[int, int, int]:
    """Decode current IR(F1..F12) back to (op4,dst4,arg8) by reading LED colors.
    - OP/DST: 1-bit per key (ON/OFF) on F1..F4 and F5..F8.
    - ARG:    2-bit per key (4-state color) on F9..F12.
    - samples: read multiple times per key and decide by majority vote.
    - use_calibration: if True and calibration data exist, use them for decoding.
    """
    # Read OP nibble
    op_bits = 0
    for i, lab in enumerate(IR_OP_1BIT):
        votes = [0, 0]
        for _ in range(max(1, samples)):
            rgb = get_key_color(lab, fresh=True)[0]
            bit_s = _nearest_1bit("OP", rgb, lab if use_calibration else None)
            votes[bit_s] += 1
        bit = 1 if votes[1] >= votes[0] else 0
        op_bits = (op_bits << 1) | bit
    # Read DST nibble
    dst_bits = 0
    for i, lab in enumerate(IR_DST_1BIT):
        votes = [0, 0]
        for _ in range(max(1, samples)):
            rgb = get_key_color(lab, fresh=True)[0]
            bit_s = _nearest_1bit("DST", rgb, lab if use_calibration else None)
            votes[bit_s] += 1
        bit = 1 if votes[1] >= votes[0] else 0
        dst_bits = (dst_bits << 1) | bit
    # Read ARG byte (pairs)
    arg_val = 0
    for i, lab in enumerate(IR_ARG_2BIT):
        votes = [0, 0, 0, 0]
        for _ in range(max(1, samples)):
            rgb = get_key_color(lab, fresh=True)[0]
            v2s = _nearest_2bit("ARG", rgb, lab if use_calibration else None)
            votes[v2s] += 1
        v2 = max(range(4), key=lambda k: votes[k])
        shift = 6 - 2*i
        arg_val |= (v2 & 0x3) << shift
    if debug:
        print(f"[IR] read op={op_bits:04b} dst={dst_bits:04b} arg={arg_val:08b} | samples={samples} cal={'Y' if use_calibration else 'N'}")
    return (op_bits & 0xF), (dst_bits & 0xF), (arg_val & 0xFF)



_MACHINE_OPS = {
    "NOP","HALT","MOV","MOVI","ADD","ADDI","SUB","SUBI",
    "AND","OR","XOR","SHL","SHR","CMP","CMPI",
    "JMP","BEQ","BNE","BMI","BPL","BVS","BVC","BCS","BCC",
}

def _is_int_literal(s: str) -> bool:
    try:
        int(s.strip().lstrip('#'), 0)
        return True
    except Exception:
        return False

def _to_int(s: str) -> int:
    t = s.strip()
    if t.startswith('#'):
        t = t[1:]
    return int(t, 0)

def encode_from_source_line(line: str) -> Tuple[int, int, int] | None:
    """한 줄 소스(라벨/고수준 포함)를 기계어 근사 형태(op4,dst4,arg8)로 변환해 IR를 갱신.
    - 가능하면 parse_line 결과에서 '기계어급' 첫 명령을 사용.
    - 전부 마이크로옵이면, 간단한 규칙으로 MOV/MOVI/ADD/ADDI/SUB/SUBI를 추정.
    """
    s = (line or "").strip()
    if not s or s.startswith('#'):
        return None
    if s.endswith(':') and (':' not in s[:-1]):
        # 라벨 줄은 IR 변경하지 않음
        return None

    try:
        ops = parse_line(s)
    except Exception:
        ops = []

    # 1) 기계어급이 있으면 그걸로 표시
    for op, args in ops:
        if str(op).upper() in _MACHINE_OPS:
            return encode_from_decoded((op, args))

    # 2) 간단 규칙으로 고수준 대입식 해석
    if '=' in s:
        left, right = [t.strip() for t in s.split('=', 1)]
        if '+' in right:
            a, b = [t.strip() for t in right.split('+', 1)]
            if left == a and _is_int_literal(b):
                return encode_from_decoded(("ADDI", (left, _to_int(b))))
            if left == b and _is_int_literal(a):
                return encode_from_decoded(("ADDI", (left, _to_int(a))))
            return encode_from_decoded(("ADD", (left, b)))
        if '-' in right:
            a, b = [t.strip() for t in right.split('-', 1)]
            if left == a and _is_int_literal(b):
                return encode_from_decoded(("SUBI", (left, _to_int(b))))
            if left == a and not _is_int_literal(b):
                return encode_from_decoded(("SUB", (left, b)))
            # 기타 케이스는 보수적으로 MOV로 표시
            return encode_from_decoded(("MOV", (left, a)))
        # 단순 대입
        if _is_int_literal(right):
            return encode_from_decoded(("MOVI", (left, _to_int(right))))
        else:
            return encode_from_decoded(("MOV", (left, right)))

    # 3) 기타는 NOP로 표시(변경 최소화)
    return encode_from_decoded(("NOP", ()))


def update_from_source_line(line: str) -> None:
    enc = encode_from_source_line(line)
    if enc is None:
        return
    op4, dst4, arg8 = enc
    set_ir(op4, dst4, arg8)


# Fixed parser for high-level source -> approximate machine tuple
# Handles negative immediates like '-1' correctly by prioritizing
# immediate detection before '+'/'-' expression handling.
def encode_from_source_line_fixed(line: str) -> Tuple[int, int, int] | None:
    s = (line or "").strip()
    if not s or s.startswith('#'):
        return None
    if s.endswith(':') and (':' not in s[:-1]):
        return None

    try:
        ops = parse_line(s)
    except Exception:
        ops = []

    for op, args in ops:
        if str(op).upper() in _MACHINE_OPS:
            return encode_from_decoded((op, args))

    if '=' in s:
        left, right = [t.strip() for t in s.split('=', 1)]
        # Detect immediates first (supports negatives and '#-3')
        if _is_int_literal(right):
            return encode_from_decoded(("MOVI", (left, _to_int(right))))
        # '+' expression
        if '+' in right:
            a, b = [t.strip() for t in right.split('+', 1)]
            if left == a and _is_int_literal(b):
                return encode_from_decoded(("ADDI", (left, _to_int(b))))
            if left == b and _is_int_literal(a):
                return encode_from_decoded(("ADDI", (left, _to_int(a))))
            return encode_from_decoded(("ADD", (left, b)))
        # '-' expression (true subtraction)
        if '-' in right:
            a, b = [t.strip() for t in right.split('-', 1)]
            if left == a and _is_int_literal(b):
                return encode_from_decoded(("SUBI", (left, _to_int(b))))
            if left == a and not _is_int_literal(b):
                return encode_from_decoded(("SUB", (left, b)))
            return encode_from_decoded(("MOV", (left, a)))
        # Simple move x = y
        return encode_from_decoded(("MOV", (left, right)))
    return encode_from_decoded(("NOP", ()))
