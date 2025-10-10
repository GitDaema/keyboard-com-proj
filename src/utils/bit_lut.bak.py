# utils/bit_lut.py

from typing import Tuple, Sequence
from utils.keyboard_presets import SRC1, SRC2, RES, STEP_LABELS, BINARY_COLORS
from openrgb.utils import RGBColor
from rgb_controller import set_labels_atomic, is_group_atomic

# 1鍮꾪듃 Full Adder ?? (A,B,Cin) -> (Sum,Cout)
# ?쇰━/?곗닠 ?곗궛???놁씠, ?쒖닔 留ㅽ븨留??ъ슜
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

# 1鍮꾪듃 Full Subtractor ?? (A,B,Bin) -> (Diff,Bout)
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

# 1鍮꾪듃 ?쇰━?곗궛 ?? (A,B) -> (Res)
AND_LUT = {("0","0"):"0", ("0","1"):"0", ("1","0"):"0", ("1","1"):"1"}
OR_LUT  = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"1"}
XOR_LUT = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"0"}


def _to_bit_str(x: int) -> str:
    # 0 -> "0", 洹???-> "1"  (遺덈━??LED?대?濡?0/1濡쒕쭔 ?ㅼ뼱??
    return "1" if int(x) != 0 else "0"

def _from_bit_str(b: str) -> int:
    return 1 if b == "1" else 0

def add8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    LED 鍮꾪듃??src1, src2瑜?LUT濡??뷀빐 dst??湲곕줉.
    - ?곗궛??+, &, ^ ?? ?놁씠 dict 議고쉶留뚯쑝濡?泥섎━.
    - 湲곕낯 媛?? 諛곗뿴??0踰??몃뜳?ㅺ? LSB.
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
        # ?④퀎 ?쒖떆: Cin -> Sum -> Cout (?쒖떆???ㅺ? ?덉쓣 ?뚮쭔)
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
    # ?쒖떆???꾧린 (?덉쑝硫?
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
    LED 鍮꾪듃??src1 - src2瑜?LUT濡?怨꾩궛??dst??湲곕줉.
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
    src瑜??쇱そ?쇰줈 1鍮꾪듃 ?쒗봽?명븯??dst??湲곕줉.
    諛?ㅻ굹??MSB(遺?몃퉬??瑜?諛섑솚. (V flag 怨꾩궛??
    """
    if lsb_first: # LSB媛 ?몃뜳??0
        msb_val = mem.get(src[7])
        for i in range(7): # 0..6
            mem.set(dst[i+1], mem.get(src[i]))
        mem.set(dst[0], 0) # LSB??0?쇰줈 梨꾩?
        return msb_val
    else: # MSB媛 ?몃뜳??0
        msb_val = mem.get(src[0])
        for i in range(7): # 0..6
            mem.set(dst[i], mem.get(src[i+1]))
        mem.set(dst[7], 0) # LSB??0?쇰줈 梨꾩?
        return msb_val

def shr8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    """
    src瑜??ㅻⅨ履쎌쑝濡?1鍮꾪듃 ?곗닠 ?쒗봽??ASR)?섏뿬 dst??湲곕줉.
    """
    if lsb_first: # LSB媛 ?몃뜳??0
        msb_val = mem.get(src[7])
        for i in range(1, 8): # 1..7
            mem.set(dst[i-1], mem.get(src[i]))
        mem.set(dst[7], msb_val) # MSB(遺?몃퉬?? 蹂댁〈
    else: # MSB媛 ?몃뜳??0
        msb_val = mem.get(src[0])
        for i in range(1, 8): # 1..7
            mem.set(dst[i], mem.get(src[i-1]))
        mem.set(dst[0], msb_val) # MSB(遺?몃퉬?? 蹂댁〈
