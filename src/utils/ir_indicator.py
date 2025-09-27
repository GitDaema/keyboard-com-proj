from typing import Dict, Tuple, Any
from openrgb.utils import RGBColor
from rgb_controller import set_labels_atomic, set_key_color
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
