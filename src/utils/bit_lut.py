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

    # 최종 자리에서 carry가 남아도 9번째 비트는 버림(8비트 오버플로우)
    # 필요하면 별도 키(예: overflow LED)에 표시하도록 확장 가능

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

def sub8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 비트열 src1 - src2를 LUT로 계산해 dst에 기록.
    - 입력/출력은 8비트, LSB부터 진행
    """
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    bin_ = "0"
    for i in idx_range:
        a = _to_bit_str(mem.get(src1[i]))
        b = _to_bit_str(mem.get(src2[i]))
        d, bout = SUB_LUT[(a, b, bin_)]
        mem.set(dst[i], _from_bit_str(d))
        bin_ = bout