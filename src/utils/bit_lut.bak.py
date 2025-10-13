# utils/bit_lut.py

from typing import Tuple, Sequence
from utils.keyboard_presets import SRC1, SRC2, RES, STEP_LABELS, BINARY_COLORS
from rgb_types import RGBColor
from rgb_controller import set_labels_atomic, is_group_atomic

# 1비트 Full Adder ?? (A,B,Cin) -> (Sum,Cout)
# ?�리/?�술 ?�산???�이, ?�수 매핑�??�용
ADD_LUT = {
    ("0","0","0"): ("0","0"),
    ("0","0","1"): ("1","0"),
    ("0","1","0"): ("1","0"),
    ("0","1","1"): ("0","1"),
    ("1","0","0"): ("1","0"),
    ("1","0","1"): ("0","1"),
    ("1","1","0"): ("0","1"),
    ("1","1","1"): ("1","1"),
}

# 1비트 Full Subtractor ?? (A,B,Bin) -> (Diff,Bout)
SUB_LUT = {
    ("0","0","0"): ("0","0"),
    ("0","0","1"): ("1","1"),
    ("0","1","0"): ("1","1"),
    ("0","1","1"): ("0","1"),
    ("1","0","0"): ("1","0"),
    ("1","0","1"): ("0","0"),
    ("1","1","0"): ("0","0"),
    ("1","1","1"): ("1","1"),
}

# 1비트 ?�리?�산 ?? (A,B) -> (Res)
AND_LUT = {("0","0"):"0", ("0","1"):"0", ("1","0"):"0", ("1","1"):"1"}
OR_LUT  = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"1"}
XOR_LUT = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"0"}


def _to_bit_str(x: int) -> str:
    # 0 -> "0", �???-> "1"  (불리??LED?��?�?0/1로만 ?�어??
    return "1" if int(x) != 0 else "0"

def _from_bit_str(b: str) -> int:
    return 1 if b == "1" else 0

def add8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 비트??src1, src2�?LUT�??�해 dst??기록.
    - ?�산??+, &, ^ ?? ?�이 dict 조회만으�?처리.
    - 기본 가?? 배열??0�??�덱?��? LSB.
    """
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    results: dict[str, int] = {}
    results: dict[str, int] = {}

    try:
        mem.set(STEP_LABELS["CIN"], 0)
        cin = "0" if int(mem.get(STEP_LABELS["CIN"])) == 0 else "1"
    except Exception:
        cin = "0"
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        s, cout = ADD_LUT[(a, b, cin)]
        # ?�계 ?�시: Cin -> Sum -> Cout (?�시???��? ?�을 ?�만)
        try:
            mem.set(STEP_LABELS["CIN"], _from_bit_str(cin))
            mem.set(STEP_LABELS["SUM"], _from_bit_str(s))
            mem.set(STEP_LABELS["COUT"], _from_bit_str(cout))
        except Exception:
            pass
        try:
            s_led = int(mem.get(STEP_LABELS["SUM"]))
        except Exception:
            s_led = _from_bit_str(s)
        if is_group_atomic():
            results[dst[i]] = int(s_led)
        else:
            mem.set(dst[i], s_led)
        try:
            cin = "0" if int(mem.get(STEP_LABELS["COUT"])) == 0 else "1"
        except Exception:
            cin = cout
    # ?�시???�기 (?�으�?
    if is_group_atomic() and results:
        payload = {}
        for lab, bit in results.items():
            on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
            rgb = on_rgb if int(bit) else off_rgb
            payload[lab] = RGBColor(*rgb)
        ok = set_labels_atomic(payload)
        if not ok:
            for lab, bit in results.items():
                try:
                    mem.set(lab, int(bit))
                except Exception:
                    pass
    return

def sub8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 비트??src1 - src2�?LUT�?계산??dst??기록.
    """
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    # Initialize borrow-in (Bin) via LED to 0
    try:
        mem.set(STEP_LABELS["CIN"], 0)
        bin_ = "0" if int(mem.get(STEP_LABELS["CIN"])) == 0 else "1"
    except Exception:
        bin_ = "0"
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        d, bout = SUB_LUT[(a, b, bin_)]
        try:
            mem.set(STEP_LABELS["CIN"], _from_bit_str(bin_))
            mem.set(STEP_LABELS["SUM"], _from_bit_str(d))
            mem.set(STEP_LABELS["COUT"], _from_bit_str(bout))
        except Exception:
            pass
        # Commit result via SUM LED
        try:
            d_led = int(mem.get(STEP_LABELS["SUM"]))
        except Exception:
            d_led = _from_bit_str(d)
        if is_group_atomic():
            results[dst[i]] = int(d_led)
        else:
            mem.set(dst[i], d_led)
        # Propagate borrow strictly through LED
        try:
            bin_ = "0" if int(mem.get(STEP_LABELS["COUT"])) == 0 else "1"
        except Exception:
            bin_ = bout
    # Preserve STEP_LABELS final state (no auto-clear)
    if is_group_atomic() and results:
        payload = {}
        for lab, bit in results.items():
            on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
            rgb = on_rgb if int(bit) else off_rgb
            payload[lab] = RGBColor(*rgb)
        ok = set_labels_atomic(payload)
        if not ok:
            for lab, bit in results.items():
                try:
                    mem.set(lab, int(bit))
                except Exception:
                    pass

def and8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    if is_group_atomic():
        results: dict[str, int] = {}
        for i in idx_range:
            a = _to_bit_str(mem.get(src1[i]))
            b = _to_bit_str(mem.get(src2[i]))
            res = AND_LUT[(a, b)]
            results[dst[i]] = _from_bit_str(res)
        if results:
            payload = {}
            for lab, bit in results.items():
                on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
                rgb = on_rgb if int(bit) else off_rgb
                payload[lab] = RGBColor(*rgb)
            ok = set_labels_atomic(payload)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        return
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = AND_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def or8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    if is_group_atomic():
        results: dict[str, int] = {}
        for i in idx_range:
            a = _to_bit_str(mem.get(src1[i]))
            b = _to_bit_str(mem.get(src2[i]))
            res = OR_LUT[(a, b)]
            results[dst[i]] = _from_bit_str(res)
        if results:
            payload = {}
            for lab, bit in results.items():
                on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
                rgb = on_rgb if int(bit) else off_rgb
                payload[lab] = RGBColor(*rgb)
            ok = set_labels_atomic(payload)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        return
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = OR_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def xor8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    if is_group_atomic():
        results: dict[str, int] = {}
        for i in idx_range:
            a = _to_bit_str(mem.get(src1[i]))
            b = _to_bit_str(mem.get(src2[i]))
            res = XOR_LUT[(a, b)]
            results[dst[i]] = _from_bit_str(res)
        if results:
            payload = {}
            for lab, bit in results.items():
                on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
                rgb = on_rgb if int(bit) else off_rgb
                payload[lab] = RGBColor(*rgb)
            ok = set_labels_atomic(payload)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        return
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = XOR_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def shl8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> int:
    """
    src�??�쪽?�로 1비트 ?�프?�하??dst??기록.
    밀?�나??MSB(부?�비??�?반환. (V flag 계산??
    """
    if lsb_first: # LSB가 ?�덱??0
        msb_val = mem.get(src[7])
        for i in range(7): # 0..6
            mem.set(dst[i+1], mem.get(src[i]))
        mem.set(dst[0], 0) # LSB??0?�로 채�?
        return msb_val
    else: # MSB가 ?�덱??0
        msb_val = mem.get(src[0])
        for i in range(7): # 0..6
            mem.set(dst[i], mem.get(src[i+1]))
        mem.set(dst[7], 0) # LSB??0?�로 채�?
        return msb_val

def shr8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    src�??�른쪽으�?1비트 ?�술 ?�프??ASR)?�여 dst??기록.
    """
    if lsb_first: # LSB가 ?�덱??0
        msb_val = mem.get(src[7])
        for i in range(1, 8): # 1..7
            mem.set(dst[i-1], mem.get(src[i]))
        mem.set(dst[7], msb_val) # MSB(부?�비?? 보존
    else: # MSB가 ?�덱??0
        msb_val = mem.get(src[0])
        for i in range(1, 8): # 1..7
            mem.set(dst[i], mem.get(src[i-1]))
        mem.set(dst[0], msb_val) # MSB(부?�비?? 보존

