from typing import Dict
from openrgb.utils import RGBColor
from rgb_controller import set_labels_atomic, set_key_color
import utils.color_presets as cp
from utils.keyboard_presets import PC as PC_LABELS


# Colors per requirement: OFF=dark gray, ON=bright orange
OFF: RGBColor = cp.DARK_GRAY
ONES_ON: RGBColor = cp.ORANGE
TENS_ON: RGBColor = cp.ORANGE_BRIGHT
EQUAL_DIGIT_ON: RGBColor = cp.BRIGHT_YELLOW  # 매우 강한 노란색


def _digit_to_label(d: int) -> str:
    """Map 0..9 to corresponding number-key label."""
    d10 = int(d) % 10
    if d10 == 0:
        return "0"
    return str(d10)


def update_pc(value: int) -> None:
    """Render PC value in decimal using number keys 1..0.

    Strategy: turn all PC labels OFF, then light the keys for the
    two decimal digits (tens and ones) in ON color. Only last two
    digits are shown (value % 100).
    """
    v = max(0, int(value))
    last2 = v % 100
    tens = (last2 // 10)
    ones = last2 % 10

    t_lab = _digit_to_label(tens)
    o_lab = _digit_to_label(ones)

    payload: Dict[str, RGBColor] = {lab: OFF for lab in PC_LABELS}

    use_tens = last2 >= 10  # 05처럼 앞자리가 0이면 켜지지 않음
    if use_tens and tens == ones:
        # 두 자리가 동일하면 해당 하나의 키만 아주 강한 노란색
        payload[o_lab] = EQUAL_DIGIT_ON
    else:
        if use_tens:
            payload[t_lab] = TENS_ON
        payload[o_lab] = ONES_ON

    ok = set_labels_atomic(payload)
    if not ok:
        # Fallback to individual updates
        for lab, col in payload.items():
            try:
                set_key_color(lab, col)
            except Exception:
                pass


def clear_pc() -> None:
    """Turn all PC labels to OFF color."""
    payload: Dict[str, RGBColor] = {lab: OFF for lab in PC_LABELS}
    ok = set_labels_atomic(payload)
    if not ok:
        for lab in PC_LABELS:
            try:
                set_key_color(lab, OFF)
            except Exception:
                pass
