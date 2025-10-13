"""bit_lut: ALU operations via LUT using keyboard LEDs.
Fast-mode supports group-atomic visual commits for SRC1/SRC2/RES.
"""

from typing import Sequence
from utils.keyboard_presets import SRC1, SRC2, RES, STEP_LABELS, BINARY_COLORS
from rgb_types import RGBColor
from rgb_controller import set_labels_atomic, is_group_atomic

# 1-bit LUTs
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

AND_LUT = {("0","0"):"0", ("0","1"):"0", ("1","0"):"0", ("1","1"):"1"}
OR_LUT  = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"1"}
XOR_LUT = {("0","0"):"0", ("0","1"):"1", ("1","0"):"1", ("1","1"):"0"}


def _to_bit_str(x: int) -> str:
    return "1" if int(x) != 0 else "0"


def _from_bit_str(b: str) -> int:
    return 1 if b == "1" else 0


def _commit_results_atomic(results: dict[str, int]) -> bool:
    if not results:
        return True
    payload = {}
    for lab, bit in results.items():
        on_rgb, off_rgb = BINARY_COLORS.get(lab, ((255, 255, 255), (0, 0, 0)))
        rgb = on_rgb if int(bit) else off_rgb
        payload[lab] = RGBColor(*rgb)
    ok = set_labels_atomic(payload)
    if not ok:
        for lab, bit in results.items():
            try:
                # Fallback through DataMemory wrapper path
                from sim.data_memory_rgb_visual import DataMemoryRGBVisual  # type: ignore
            except Exception:
                pass
    return ok


def add8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
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
    if is_group_atomic():
        ok = _commit_results_atomic(results)
        if not ok:
            for lab, bit in results.items():
                try:
                    mem.set(lab, int(bit))
                except Exception:
                    pass
    return


def sub8_via_lut(mem, *, src1: Sequence[str] = SRC1, src2: Sequence[str] = SRC2, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    idx_range = range(0, 8) if lsb_first else range(7, -1, -1)
    results: dict[str, int] = {}
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
        try:
            d_led = int(mem.get(STEP_LABELS["SUM"]))
        except Exception:
            d_led = _from_bit_str(d)
        if is_group_atomic():
            results[dst[i]] = int(d_led)
        else:
            mem.set(dst[i], d_led)
        try:
            bin_ = "0" if int(mem.get(STEP_LABELS["COUT"])) == 0 else "1"
        except Exception:
            bin_ = bout
    if is_group_atomic():
        ok = _commit_results_atomic(results)
        if not ok:
            for lab, bit in results.items():
                try:
                    mem.set(lab, int(bit))
                except Exception:
                    pass
    return


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
            ok = _commit_results_atomic(results)
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
            ok = _commit_results_atomic(results)
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
            ok = _commit_results_atomic(results)
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
    if lsb_first:
        msb_val = mem.get(src[7])
        if is_group_atomic():
            results: dict[str, int] = {}
            for i in range(7):
                results[dst[i+1]] = int(mem.get(src[i]))
            results[dst[0]] = 0
            ok = _commit_results_atomic(results)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        else:
            for i in range(7):
                mem.set(dst[i+1], mem.get(src[i]))
            mem.set(dst[0], 0)
        return msb_val
    else:
        msb_val = mem.get(src[0])
        if is_group_atomic():
            results: dict[str, int] = {}
            for i in range(7):
                results[dst[i]] = int(mem.get(src[i+1]))
            results[dst[7]] = 0
            ok = _commit_results_atomic(results)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        else:
            for i in range(7):
                mem.set(dst[i], mem.get(src[i+1]))
            mem.set(dst[7], 0)
        return msb_val


def shr8_via_lut(mem, *, src: Sequence[str] = SRC1, dst: Sequence[str] = RES,
                 lsb_first: bool = True) -> None:
    if lsb_first:
        msb_val = mem.get(src[7])
        if is_group_atomic():
            results: dict[str, int] = {}
            for i in range(1, 8):
                results[dst[i-1]] = int(mem.get(src[i]))
            results[dst[7]] = int(msb_val)
            ok = _commit_results_atomic(results)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        else:
            for i in range(1, 8):
                mem.set(dst[i-1], mem.get(src[i]))
            mem.set(dst[7], msb_val)
    else:
        msb_val = mem.get(src[0])
        if is_group_atomic():
            results: dict[str, int] = {}
            for i in range(1, 8):
                results[dst[i]] = int(mem.get(src[i-1]))
            results[dst[0]] = int(msb_val)
            ok = _commit_results_atomic(results)
            if not ok:
                for lab, bit in results.items():
                    try:
                        mem.set(lab, int(bit))
                    except Exception:
                        pass
        else:
            for i in range(1, 8):
                mem.set(dst[i], mem.get(src[i-1]))
            mem.set(dst[0], msb_val)

