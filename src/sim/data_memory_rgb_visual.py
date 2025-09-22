# sim/data_memory_rgb_visual.py
from rgb_controller import set_key_color, get_key_color
from openrgb.utils import RGBColor
from utils.keyboard_presets import VARIABLE_KEYS

# 거리 계산에서 G는 가시성 보조 채널이므로 가중치를 낮게 둔다.
WG = 0.5  # R,B는 1.0, G는 0.5

def _wrap_s8(x: int) -> int:
    return ((int(x) + 128) & 0xFF) - 128

# ── 새로운 색상 생성 로직 ────────────────────────────────────────
# 양수: 빨강 → 노랑 스펙트럼
# 음수: 파랑 → 청록 스펙트럼
# 0: 중간 회색
# 이로써 양수와 음수의 색상 구별을 명확히 하여 혼동을 방지한다.

VALS   = list(range(-128, 128))
VAL_TO_RGB_LIST: list[tuple[int, int, int]] = []
RGB_TO_VAL_EXACT: dict[tuple[int, int, int], int] = {}

for v in VALS:
    r, g, b = 0, 0, 0
    if v == 0:
        r, g, b = 128, 128, 128
    elif v > 0:
        # 양수: 빨강(255,0,0)에서 노랑(255,255,0)으로
        t = v / 127.0  # 0..1
        r = 255
        g = int(t * 255)
        b = 0
    else:  # v < 0
        # 음수: 파랑(0,0,255)에서 청록(0,255,255)으로
        t = abs(v) / 128.0  # 0..1
        r = 0
        g = int(t * 255)
        b = 255
    
    rgb = (r, g, b)
    VAL_TO_RGB_LIST.append(rgb)
    RGB_TO_VAL_EXACT[rgb] = v

def _nearest_val_from_rgb(r: int, g: int, b: int) -> int:
    '''임의의 (r,g,b) 측정값을 가장 가까운 LUT 항목으로 스냅.'''
    tup = (int(r), int(g), int(b))
    if tup in RGB_TO_VAL_EXACT:
        return RGB_TO_VAL_EXACT[tup]
    
    best_idx = 0
    best_d2 = 10**12
    for i, (rr, gg, bb) in enumerate(VAL_TO_RGB_LIST):
        dr = r - rr
        dg = g - gg
        db = b - bb
        # G 채널의 가중치를 낮추는 로직은 그대로 유지
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