from typing import Literal
import threading
from openrgb.utils import RGBColor
from rgb_controller import set_labels_atomic, set_key_color
import utils.color_presets as cp

# Control stage -> arrow key mapping (left=DECODE, right=WRITEBACK)
STAGE_KEYS: dict[str, str] = {
    "FETCH": "up",
    "DECODE": "left",
    "EXECUTE": "down",
    "WRITEBACK": "right",
}

STAGES = ("FETCH", "DECODE", "EXECUTE", "WRITEBACK")

# Single unique ON color for all stages
STAGE_ON: RGBColor = cp.CYAN
STAGE_OFF: RGBColor = cp.BLACK

StageName = Literal["FETCH", "DECODE", "EXECUTE", "WRITEBACK"]

# 내부 상태: 각 단계가 '한번이라도 표시됨' 여부와 현재 점등 상태
_shown: dict[str, bool] = {s: False for s in STAGES}
_on: dict[str, bool] = {s: False for s in STAGES}
_lock = threading.Lock()

def clear_stages() -> None:
    with _lock:
        payload = {lab: STAGE_OFF for lab in STAGE_KEYS.values()}
    ok = set_labels_atomic(payload)
    if not ok:
        for lab in payload.keys():
            try:
                set_key_color(lab, STAGE_OFF)
            except Exception:
                pass
    with _lock:
        for s in STAGES:
            _on[s] = False
            _shown[s] = False

def post_stage(stage: StageName) -> None:
    """
    단순 규칙:
    - 새 stage는 즉시 켠다(성공하면 해당 단계는 '표시됨'으로 기록).
    - 현재 단계가 아닌 키는 '표시된 적이 있다면' 즉시 끈다.
    - 동시에 여러 키가 켜져 있는 것은 허용됨.
    """
    target = STAGE_KEYS.get(stage)
    if not target:
        return

    with _lock:
        # 끌 목록: 이미 표시되었고 현재 단계가 아닌 것들
        off_labels = []
        for s in STAGES:
            if s != stage and _on[s] and _shown[s]:
                off_labels.append(STAGE_KEYS[s])

        # 켤 대상 포함한 일괄 페이로드 구성
        payload = {target: STAGE_ON}
        for lab in off_labels:
            payload[lab] = STAGE_OFF

    ok = set_labels_atomic(payload)
    if ok:
        with _lock:
            _on[stage] = True
            _shown[stage] = True
            for s in STAGES:
                if s != stage and STAGE_KEYS[s] in off_labels:
                    _on[s] = False
        return

    # 배치 실패 시 개별 폴백
    try:
        set_key_color(target, STAGE_ON)
        turned_on = True
    except Exception:
        turned_on = False

    with _lock:
        if turned_on:
            _on[stage] = True
            _shown[stage] = True
        for lab in off_labels:
            try:
                set_key_color(lab, STAGE_OFF)
                # 역매핑으로 _on 갱신
                for s in STAGES:
                    if STAGE_KEYS[s] == lab:
                        _on[s] = False
            except Exception:
                pass
