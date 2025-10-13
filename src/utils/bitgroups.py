from typing import Sequence, List, Tuple
from rgb_types import RGBColor
from rgb_controller import set_key_color, get_key_color  # ê¸°ì¡´ ê³µê°œ API ?¬ì‚¬??
import utils.color_presets as cp

def _value_to_bits_lsb(n: int, width: int) -> List[int]:
    if n < 0:
        raise ValueError("?Œìˆ˜??ì§€?í•˜ì§€ ?ŠìŠµ?ˆë‹¤.")
    return [ (n >> i) & 1 for i in range(width) ]  # LSBë¶€??

def _bitstring_msb(bits_lsb: Sequence[int]) -> str:
    # ?”ë©´/ë¡œê·¸?? ??ƒ MSB?’LSB ?œì„œë¡?ë¬¸ì???Œë”ë§?
    return "".join("1" if b else "0" for b in reversed(bits_lsb))

def copy_group_value(
    src_labels: Sequence[str],
    dst_labels: Sequence[str],
    *,
    on_color: RGBColor = cp.WHITE,
    off_color: RGBColor = cp.BLACK,
    lsb_first: bool = False,
    debug: bool = False
):
    """
    src_labels: ?ë³¸ LED ê·¸ë£¹
    dst_labels: ë³µì‚¬ ?€??LED ê·¸ë£¹
    return: (ë³µì‚¬??ê°? ë¹„íŠ¸ë¬¸ì?? ì¼œì§„ ??ëª©ë¡)
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
    lsb_first: bool = False,
    debug: bool = False,
) -> Tuple[int, str, List[str], bool]:
    """
    labels: ???¼ë²¨ ëª©ë¡ (?? ["1","2","3","4","5","6","7","8"])
    n: ?œì‹œ???•ìˆ˜ê°?
    lsb_first: labels[0]??LSB?¸ì? ?¬ë?
    return: (?¤ì œ?ìš©ê°? ë¹„íŠ¸ë¬¸ì??MSB?’LSB), ì¼œì§„?¤ëª©ë¡? overflow_masked)
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
        # ???¤ë§Œ ë°”ê¾¸??ê¸°ì¡´ APIë¥?ê·¸ë?ë¡??¬ìš©
        set_key_color(label, color)
        if b:
            on_labels.append(label)

    bitstr = _bitstring_msb(bits_lsb)
    if debug:
        # ?? [BIT] 13 -> 00001101 (ON: 1, 3, 4)
        on_list = ", ".join(on_labels) if on_labels else "-"
        note = " [OVERFLOW MASKED]" if overflow_masked else ""
        print(f"[BIT] {value} -> {bitstr} (ON: {on_list}){note}")

    return value, bitstr, on_labels, overflow_masked

def get_group_value(
    labels: Sequence[str],
    *,
    threshold: int = 70,   # 0~255, ?‰ê·  ë°ê¸°( (R+G+B)/3 ) ?„ê³„ì¹?
    lsb_first: bool = False, # labels[0]??LSB?¸ì? ?¬ë?
    fresh: bool = True,     # ë§¤ë²ˆ ?¥ì¹˜?ì„œ ?ˆë¡œ ?½ì„ì§€
    debug: bool = False
) -> Tuple[int, List[int], List[str]]:
    """
    returns: (value, bits_lsb, on_labels)
      - value: ?•ìˆ˜ê°?
      - bits_lsb: LSB?’MSB ?œì„œ ë¹„íŠ¸ ë¦¬ìŠ¤??
      - on_labels: 1(ì¼œì§)ë¡??ì •???¼ë²¨ ëª©ë¡
    """
    # ?œíšŒ ?œì„œ ê²°ì •
    order = list(labels) if lsb_first else list(reversed(labels))

    bits_lsb: List[int] = []
    on_labels: List[str] = []

    for idx, lab in enumerate(order):
        # Refresh device at most once per group read to reduce overhead
        do_fresh = bool(fresh) and (idx == 0)
        (r, g, b) = get_key_color(lab, fresh=do_fresh)[0]  # (R,G,B)
        on = ((r + g + b) / 3.0) >= threshold
        bit = 1 if on else 0
        bits_lsb.append(bit)
        if on:
            on_labels.append(lab)

    # LSB ê¸°ì? ?•ìˆ˜ë¡?ë³€??
    value = 0
    for i, bit in enumerate(bits_lsb):
        value |= (bit << i)

    if debug:
        bitstr_msb = "".join("1" if b else "0" for b in reversed(bits_lsb))
        on_list = ", ".join(on_labels) if on_labels else "-"
        print(f"[READ] {value} <- {bitstr_msb} (ON: {on_list}, thr={threshold})")

    return value, bits_lsb, on_labels

