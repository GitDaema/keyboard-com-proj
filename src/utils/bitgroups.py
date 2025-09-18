from typing import Sequence, List, Tuple
from openrgb.utils import RGBColor
from rgb_controller import set_key_color, get_key_color  # 기존 공개 API 재사용
import utils.color_presets as cp

def _value_to_bits_lsb(n: int, width: int) -> List[int]:
    if n < 0:
        raise ValueError("음수는 지원하지 않습니다.")
    return [ (n >> i) & 1 for i in range(width) ]  # LSB부터

def _bitstring_msb(bits_lsb: Sequence[int]) -> str:
    # 화면/로그용: 항상 MSB→LSB 순서로 문자열 렌더링
    return "".join("1" if b else "0" for b in reversed(bits_lsb))

def copy_group_value(
    src_labels: Sequence[str],
    dst_labels: Sequence[str],
    *,
    on_color: RGBColor = cp.WHITE,
    off_color: RGBColor = cp.BLACK,
    lsb_first: bool = True,
    debug: bool = False
):
    """
    src_labels: 원본 LED 그룹
    dst_labels: 복사 대상 LED 그룹
    return: (복사된 값, 비트문자열, 켜진 키 목록)
    """
    val, _, _ = get_group_value(src_labels, lsb_first=lsb_first, debug=debug)
    return set_group_value(dst_labels, val, on_color, off_color,
                           lsb_first=lsb_first, debug=debug)

def set_group_value(
    labels: Sequence[str],
    n: int,
    on_color: RGBColor = cp.WHITE,
    off_color: RGBColor = cp.BLACK,
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

def get_group_value(
    labels: Sequence[str],
    *,
    threshold: int = 70,   # 0~255, 평균 밝기( (R+G+B)/3 ) 임계치
    lsb_first: bool = True, # labels[0]이 LSB인지 여부
    fresh: bool = True,     # 매번 장치에서 새로 읽을지
    debug: bool = False
) -> Tuple[int, List[int], List[str]]:
    """
    returns: (value, bits_lsb, on_labels)
      - value: 정수값
      - bits_lsb: LSB→MSB 순서 비트 리스트
      - on_labels: 1(켜짐)로 판정된 라벨 목록
    """
    # 순회 순서 결정
    order = list(labels) if lsb_first else list(reversed(labels))

    bits_lsb: List[int] = []
    on_labels: List[str] = []

    for lab in order:
        (r, g, b) = get_key_color(lab, fresh=fresh)[0]  # (R,G,B)
        on = ((r + g + b) / 3.0) >= threshold
        bit = 1 if on else 0
        bits_lsb.append(bit)
        if on:
            on_labels.append(lab)

    # LSB 기준 정수로 변환
    value = 0
    for i, bit in enumerate(bits_lsb):
        value |= (bit << i)

    if debug:
        bitstr_msb = "".join("1" if b else "0" for b in reversed(bits_lsb))
        on_list = ", ".join(on_labels) if on_labels else "-"
        print(f"[READ] {value} <- {bitstr_msb} (ON: {on_list}, thr={threshold})")

    return value, bits_lsb, on_labels