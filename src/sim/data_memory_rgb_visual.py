# sim/data_memory_rgb_visual.py
from rgb_controller import set_key_color, get_key_color
from openrgb.utils import RGBColor
from utils.keyboard_presets import VARIABLE_KEYS
import time

# 거리 계산에서 G 채널은 낮은 가중치를 둬서 R/B 악센트 차이를 더 잘 반영
WG = 0.3  # R,B=1.0, G=0.3

def _wrap_s8(x: int) -> int:
    return ((int(x) + 128) & 0xFF) - 128

# 값 -> 색상 매핑(가시성 강화)
# - 작은 정수 변화도 식별되도록 mod16 악센트(두 채널)에 큰 스텝을 부여
# - 0은 밝은 회색, 모든 채널 최소 50 이상으로 검정 근접 방지
VALS   = list(range(-128, 128))
VAL_TO_RGB_LIST: list[tuple[int, int, int]] = []
RGB_TO_VAL_EXACT: dict[tuple[int, int, int], int] = {}

def _clamp(x: int, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, int(x)))

for v in VALS:
    if v == 0:
        rgb = (190, 190, 190)
    elif v > 0:
        # 양수: R=255 유지, G는 sqrt 스케일(초기 민감도↑), B는 mod16 악센트로 미세 변화 증폭
        mag = v / 127.0
        n = v & 0x0F  # 0..15
        g = _clamp(int((mag ** 0.5) * 180) + 60, 60, 255)
        r = 255 - min(32, n * 2)                 # 255..223 (약한 변화)
        b = _clamp(50 + n * 13, 50, 255)         # 50..255 (강한 변화)
        rgb = (r, g, b)
    else:
        # 음수: B=255 유지, G는 sqrt 스케일, R는 mod16 악센트
        av = abs(v)
        n = av & 0x0F  # 0..15
        mag = av / 128.0
        g = _clamp(int((mag ** 0.5) * 180) + 60, 60, 255)
        b = 255 - min(32, n * 2)                 # 255..223
        r = _clamp(50 + n * 13, 50, 255)         # 50..255
        rgb = (r, g, b)

    VAL_TO_RGB_LIST.append(rgb)
    RGB_TO_VAL_EXACT[rgb] = v

def _nearest_val_from_rgb(r: int, g: int, b: int) -> int:
    """입력(r,g,b) 측정값을 가장 가까운 LUT 인덱스로 매핑."""
    tup = (int(r), int(g), int(b))
    if tup in RGB_TO_VAL_EXACT:
        return RGB_TO_VAL_EXACT[tup]

    best_idx = 0
    best_d2 = 10**12
    for i, (rr, gg, bb) in enumerate(VAL_TO_RGB_LIST):
        dr = r - rr
        dg = g - gg
        db = b - bb
        # G 채널의 가중치는 낮춰서 R/B 차이를 강조
        d2 = (dr*dr) + (WG * dg*dg) + (db*db)
        if d2 < best_d2:
            best_d2 = d2
            best_idx = i
    return VALS[best_idx]

class DataMemoryRGBVisual:
    def __init__(self, *, binary_labels=None, samples: int = 3, sample_delay_ms: int = 0, debug: bool = False) -> None:
        self._binary = dict(binary_labels) if binary_labels else {}
        for k in VARIABLE_KEYS:
            if k in self._binary:
                del self._binary[k]
        self._samples = int(samples) if int(samples) >= 1 else 1
        self._delay = int(sample_delay_ms) if int(sample_delay_ms) >= 0 else 0
        self._debug = bool(debug)

    def _sleep(self):
        if self._delay > 0:
            time.sleep(self._delay / 1000.0)

    def _read_rgb_multi(self, name: str) -> tuple[int, int, int]:
        """Read RGB multiple times with optional early exit if stable.
        - Refresh device once, then reuse cached state for subsequent samples in the window.
        - If the first two samples are very close, skip remaining samples to save time.
        """
        rs = gs = bs = 0
        n = max(1, self._samples)
        prev: tuple[int, int, int] | None = None
        fresh = True
        taken = 0
        for i in range(n):
            r, g, b = get_key_color(name, fresh=fresh)[0]
            fresh = False  # avoid repeated full-device refreshes within the same read window
            rs += int(r); gs += int(g); bs += int(b)
            taken += 1
            # Early-exit: if two consecutive samples are nearly identical, stop
            if prev is not None:
                dr = abs(int(r) - prev[0])
                dg = abs(int(g) - prev[1])
                db = abs(int(b) - prev[2])
                if dr <= 3 and dg <= 3 and db <= 3:
                    break
            prev = (int(r), int(g), int(b))
            self._sleep()
        if taken <= 0:
            return (0, 0, 0)
        return (rs // taken, gs // taken, bs // taken)

    def get(self, name: str) -> int:
        if name in self._binary:
            # Majority vote over multiple samples for robust bit read
            on_rgb, off_rgb = self._binary[name]
            def d2(px, py):
                dr, dg, db = px[0]-py[0], px[1]-py[1], px[2]-py[2]
                return (dr*dr) + (WG*dg*dg) + (db*db)
            votes_on = 0
            votes_off = 0
            n = max(1, self._samples)
            fresh = True
            for i in range(n):
                r, g, b = get_key_color(name, fresh=fresh)[0]
                fresh = False  # refresh once at the start
                if d2((r,g,b), on_rgb) <= d2((r,g,b), off_rgb):
                    votes_on += 1
                else:
                    votes_off += 1
                # Early exit: if first two samples already agree, skip third
                if n >= 3 and i == 1 and (votes_on == 2 or votes_off == 2):
                    break
                self._sleep()
            bit = 1 if votes_on >= votes_off else 0
            if self._debug:
                print(f"[RGBMem] get-bit {name}: on={votes_on} off={votes_off} -> {bit}")
            return bit
        # For numeric variables, average RGB and map to nearest LUT color
        r, g, b = self._read_rgb_multi(name)
        v = _nearest_val_from_rgb(r, g, b)
        val = _wrap_s8(v)
        if self._debug:
            print(f"[RGBMem] get-val {name}: avg=({r},{g},{b}) -> {val}")
        return val

    def set(self, name: str, val: int) -> None:
        if name in self._binary:
            on_rgb, off_rgb = self._binary[name]
            tgt = on_rgb if int(val) != 0 else off_rgb
            set_key_color(name, RGBColor(*tgt))
            return
        v = _wrap_s8(val)
        idx = v - (-128)
        r, g, b = VAL_TO_RGB_LIST[idx]
        set_key_color(name, RGBColor(r, g, b))

    def set_flag(self, label: str, on: bool) -> None:
        self.set(label, 1 if on else 0)

    def get_flag(self, label: str) -> bool:
        return bool(self.get(label))
