# sim/data_memory_rgb_visual.py
from rgb_controller import set_key_color, get_key_color
from openrgb.utils import RGBColor

# 거리 계산에서 G는 가시성 보조 채널이므로 가중치를 낮게 둔다.
WG = 0.5  # R,B는 1.0, G는 0.5

def _wrap_s8(x: int) -> int:
    return ((int(x) + 128) & 0xFF) - 128

def _clamp255(x: float) -> int:
    x = int(round(x))
    return 0 if x < 0 else (255 if x > 255 else x)

# ── 가시성 규칙(화이트 블렌딩) ────────────────────────────────────────
# 0에 가까울수록 "밝은 하양"에 강하게 섞이고, |v|가 커질수록 본색(R/B) 위주.
# - 양수(+): R 채널↑
# - 음수(−): B 채널↑
# 화이트 블렌딩 계수 w는 [WHITEN_MIN, WHITEN_MAX] 범위에서
#   w = WHITEN_MIN + (1 - |v|/128) * (WHITEN_MAX - WHITEN_MIN)
# 로 결정. v≈0일 때 w≈WHITEN_MAX → 거의 하양, ±극값에서 w≈WHITEN_MIN → 본색 유지.
WHITEN_MIN = 0.00   # ±극값에서의 최소 화이트 섞임(0.0~1.0)
WHITEN_MAX = 0.90   # 0 근처에서의 최대 화이트 섞임(0.0~1.0)

VALS   = list(range(-128, 128))
VAL_TO_RGB_LIST: list[tuple[int, int, int]] = []
RGB_TO_VAL_EXACT: dict[tuple[int, int, int], int] = {}

for v in VALS:
    # 1) 부호에 따른 기본색(양수=빨강, 음수=파랑)
    pos = max(0.0,  v) / 127.0   # v>0일 때 0..1
    neg = max(0.0, -v) / 128.0   # v<0일 때 0..1
    base_r = 255.0 * pos
    base_g = 0.0                 # 기본색 단계에선 G=0 (화이트 섞이면서 G가 생김)
    base_b = 255.0 * neg

    # 2) 0 근처 밝기 강조를 위한 화이트(255,255,255) 블렌딩
    t = abs(v) / 128.0                      # 0..1 (클수록 극값)
    w = WHITEN_MIN + (1.0 - t) * (WHITEN_MAX - WHITEN_MIN)  # 0~1
    r = _clamp255((1.0 - w) * base_r + w * 255.0)
    g = _clamp255((1.0 - w) * base_g + w * 255.0)
    b = _clamp255((1.0 - w) * base_b + w * 255.0)

    rgb = (r, g, b)
    VAL_TO_RGB_LIST.append(rgb)
    RGB_TO_VAL_EXACT[rgb] = v  # 정확히 같은 값으로 세팅했다면 역변환을 O(1)로

def _nearest_val_from_rgb(r: int, g: int, b: int) -> int:
    """임의의 (r,g,b) 측정값을 가장 가까운 LUT 항목으로 스냅."""
    tup = (int(r), int(g), int(b))
    # 1) 먼저 완전 일치이면 바로 반환
    if tup in RGB_TO_VAL_EXACT:
        return RGB_TO_VAL_EXACT[tup]

    # 2) 아니면 근접 탐색(유클리드 거리, G에 낮은 가중치)
    best_idx = 0
    best_d2 = 10**12
    for i, (rr, gg, bb) in enumerate(VAL_TO_RGB_LIST):
        dr = r - rr
        dg = g - gg
        db = b - bb
        d2 = (dr*dr) + (WG * dg*dg) + (db*db)
        if d2 < best_d2:
            best_d2 = d2
            best_idx = i
    return VALS[best_idx]

class DataMemoryRGBVisual:
    """
    변수 이름 == LED 라벨(키 이름) 가정.
    - set(name, val): signed 8비트(-128..127)를 LUT의 RGB로 '정확히' 기록
    - get(name)     : LED RGB를 읽어 가장 가까운 LUT 항목으로 스냅해 -128..127 복원
    """

    def __init__(self, *, binary_labels=None) -> None:
        # 불리언 전용 라벨: {label: (on_rgb, off_rgb)}
        self._binary = binary_labels or {}

    def get(self, name: str) -> int:
        r, g, b = get_key_color(name, fresh=True)[0]
        # 불리언 전용 라벨이면 on/off 판정
        if name in self._binary:
            on_rgb, off_rgb = self._binary[name]
            def d2(px, py):
                dr, dg, db = px[0]-py[0], px[1]-py[1], px[2]-py[2]
                return (dr*dr) + (WG*dg*dg) + (db*db)
            return 1 if d2((r,g,b), on_rgb) <= d2((r,g,b), off_rgb) else 0
        # 일반 값은 LUT 기반
        v = _nearest_val_from_rgb(r, g, b)
        return _wrap_s8(v)

    def set(self, name: str, val: int) -> None:
        # 불리언 전용 라벨이면 on/off 색 직접 출력
        if name in self._binary:
            on_rgb, off_rgb = self._binary[name]
            tgt = on_rgb if int(val) != 0 else off_rgb
            set_key_color(name, RGBColor(*tgt))
            return
        # 일반 값은 LUT 기반
        v = _wrap_s8(val)
        idx = v - (-128)
        r, g, b = VAL_TO_RGB_LIST[idx]
        set_key_color(name, RGBColor(r, g, b))

    # 헬퍼
    def set_flag(self, label: str, on: bool) -> None:
        self.set(label, 1 if on else 0)

    def get_flag(self, label: str) -> bool:
        return bool(self.get(label))
