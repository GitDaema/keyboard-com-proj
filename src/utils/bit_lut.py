# utils/bit_lut.py

from typing import Tuple, Sequence
from utils.keyboard_presets import SRC1, SRC2, RES

# 1비트 Full Adder 표: (A,B,Cin) -> (Sum,Cout)
# 논리/산술 연산자 없이, 순수 매핑만 사용
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

# 1비트 Full Subtractor 표: (A,B,Bin) -> (Diff,Bout)
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

# 1비트 논리연산 표: (A,B) -> (Res)
AND_LUT = {("0","0"):"0", ("0","1"):"0", ("1","0"):"0", ("1","1"):"1"}
OR_LUT  = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"1"}
XOR_LUT = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"0"}


def _to_bit_str(x: int) -> str:
    # 0 -> "0", 그 외 -> "1"  (불리언 LED이므로 0/1로만 들어옴)
    return "1" if int(x) != 0 else "0"

def _from_bit_str(b: str) -> int:
    return 1 if b == "1" else 0

def add8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 비트열 src1, src2를 LUT로 더해 dst에 기록.
    - 연산자(+, &, ^ 등) 없이 dict 조회만으로 처리.
    - 기본 가정: 배열의 0번 인덱스가 LSB.
    """
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)

    cin = "0"
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        s, cout = ADD_LUT[(a, b, cin)]
        mem.set(dst[i], _from_bit_str(s))
        cin = cout

def sub8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 비트열 src1 - src2를 LUT로 계산해 dst에 기록.
    """
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    bin_ = "0"
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        d, bout = SUB_LUT[(a, b, bin_)]
        mem.set(dst[i], _from_bit_str(d))
        bin_ = bout

def and8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = AND_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def or8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = OR_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def xor8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        res = XOR_LUT[(a, b)]
        mem.set(dst[i], _from_bit_str(res))

def shl8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> int:
    """
    src를 왼쪽으로 1비트 시프트하여 dst에 기록.
    밀려나는 MSB(부호비트)를 반환. (V flag 계산용)
    """
    if lsb_first: # LSB가 인덱스 0
        msb_val = mem.get(src[7])
        for i in range(7): # 0..6
            mem.set(dst[i+1], mem.get(src[i]))
        mem.set(dst[0], 0) # LSB는 0으로 채움
        return msb_val
    else: # MSB가 인덱스 0
        msb_val = mem.get(src[0])
        for i in range(7): # 0..6
            mem.set(dst[i], mem.get(src[i+1]))
        mem.set(dst[7], 0) # LSB는 0으로 채움
        return msb_val

def shr8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    src를 오른쪽으로 1비트 산술 시프트(ASR)하여 dst에 기록.
    """
    if lsb_first: # LSB가 인덱스 0
        msb_val = mem.get(src[7])
        for i in range(1, 8): # 1..7
            mem.set(dst[i-1], mem.get(src[i]))
        mem.set(dst[7], msb_val) # MSB(부호비트) 보존
    else: # MSB가 인덱스 0
        msb_val = mem.get(src[0])
        for i in range(1, 8): # 1..7
            mem.set(dst[i], mem.get(src[i-1]))
        mem.set(dst[0], msb_val) # MSB(부호비트) 보존
