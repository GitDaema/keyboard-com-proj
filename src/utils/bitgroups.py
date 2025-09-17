from typing import Sequence, List, Tuple
from openrgb.utils import RGBColor
from rgb_controller import set_key_color  # 기존 공개 API 재사용

def _value_to_bits_lsb(n: int, width: int) -> List[int]:
    if n < 0:
        raise ValueError("음수는 지원하지 않습니다.")
    return [ (n >> i) & 1 for i in range(width) ]  # LSB부터

def _bitstring_msb(bits_lsb: Sequence[int]) -> str:
    # 화면/로그용: 항상 MSB→LSB 순서로 문자열 렌더링
    return "".join("1" if b else "0" for b in reversed(bits_lsb))

def set_group_value(
    labels: Sequence[str],
    n: int,
    on_color: RGBColor = RGBColor(255, 255, 255),
    off_color: RGBColor = RGBColor(0, 0, 0),
    *,
    lsb_first: bool = True,
    debug: bool = False,
) -> Tuple[int, str, List[str], bool]:
    """
    labels: 키 라벨 목록 (예: ["1","2","3","4","5","6","7","8"])
    n: 표시할 정수값
    lsb_first: labels[0]이 LSB인지 여부
    return: (실제적용값, 비트문자열(MSB→LSB), 켜진키목록, overflow_masked)
    """
    width = len(labels)
    mask = (1 << width) - 1
    overflow_masked = n > mask
    value = n & mask

    bits_lsb = _value_to_bits_lsb(value, width)

    on_labels: List[str] = []
    for pos, label in enumerate(labels):
        b = bits_lsb[pos] if lsb_first else bits_lsb[width - 1 - pos]
        color = on_color if b else off_color
        # 한 키만 바꾸는 기존 API를 그대로 사용
        set_key_color(label, color)
        if b:
            on_labels.append(label)

    bitstr = _bitstring_msb(bits_lsb)
    if debug:
        # 예: [BIT] 13 -> 00001101 (ON: 1, 3, 4)
        on_list = ", ".join(on_labels) if on_labels else "-"
        note = " [OVERFLOW MASKED]" if overflow_masked else ""
        print(f"[BIT] {value} -> {bitstr} (ON: {on_list}){note}")

    return value, bitstr, on_labels, overflow_masked