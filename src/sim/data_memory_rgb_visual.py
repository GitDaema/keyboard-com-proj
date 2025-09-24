# sim/data_memory_rgb_visual.py
from rgb_controller import set_key_color, get_key_color
from openrgb.utils import RGBColor
from utils.keyboard_presets import VARIABLE_KEYS

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
    def __init__(self, *, binary_labels=None) -> None:
        self._binary = dict(binary_labels) if binary_labels else {}
        for k in VARIABLE_KEYS:
            if k in self._binary:
                del self._binary[k]

    def get(self, name: str) -> int:
        r, g, b = get_key_color(name, fresh=True)[0]
        if name in self._binary:
            on_rgb, off_rgb = self._binary[name]
            def d2(px, py):
                dr, dg, db = px[0]-py[0], px[1]-py[1], px[2]-py[2]
                return (dr*dr) + (WG*dg*dg) + (db*db)
            return 1 if d2((r,g,b), on_rgb) <= d2((r,g,b), off_rgb) else 0
        v = _nearest_val_from_rgb(r, g, b)
        return _wrap_s8(v)

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

