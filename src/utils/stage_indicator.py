from typing import Literal
import threading
from rgb_types import RGBColor
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

# ?´ë? ?íƒœ: ê°??¨ê³„ê°€ '?œë²ˆ?´ë¼???œì‹œ?? ?¬ë??€ ?„ì¬ ?ë“± ?íƒœ
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
    ?¨ìˆœ ê·œì¹™:
    - ??stage??ì¦‰ì‹œ ì¼ ë‹¤(?±ê³µ?˜ë©´ ?´ë‹¹ ?¨ê³„??'?œì‹œ???¼ë¡œ ê¸°ë¡).
    - ?„ì¬ ?¨ê³„ê°€ ?„ë‹Œ ?¤ëŠ” '?œì‹œ???ì´ ?ˆë‹¤ë©? ì¦‰ì‹œ ?ˆë‹¤.
    - ?™ì‹œ???¬ëŸ¬ ?¤ê? ì¼œì ¸ ?ˆëŠ” ê²ƒì? ?ˆìš©??
    """
    target = STAGE_KEYS.get(stage)
    if not target:
        return

    with _lock:
        # ??ëª©ë¡: ?´ë? ?œì‹œ?˜ì—ˆê³??„ì¬ ?¨ê³„ê°€ ?„ë‹Œ ê²ƒë“¤
        off_labels = []
        for s in STAGES:
            if s != stage and _on[s] and _shown[s]:
                off_labels.append(STAGE_KEYS[s])

        # ì¼??€???¬í•¨???¼ê´„ ?˜ì´ë¡œë“œ êµ¬ì„±
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

    # ë°°ì¹˜ ?¤íŒ¨ ??ê°œë³„ ?´ë°±
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
                # ??§¤?‘ìœ¼ë¡?_on ê°±ì‹ 
                for s in STAGES:
                    if STAGE_KEYS[s] == lab:
                        _on[s] = False
            except Exception:
                pass

