# -*- coding: utf-8 -*-
"""
LED 이름(JSON) -> 라벨(label) 매핑 생성기
- 입력: src/maps/*_leds.json   (export_led_map.py 결과)
- 출력: src/maps/label_map.json

동작:
1) 이름 정규화(norm) 후, ALIASES에 정의된 별칭들을 우선 매칭
2) F키/숫자열/방향키/편집키/미디어키는 규칙 매칭(heuristics)로 보완
3) 중복(ambiguous) 발생 시 candidates로 보고 -> label_map.json에서 사람이 1회 정정

라벨 예:
  "esc", "f1"~"f12", "grave", "num_1"~"num_0",
  "tab","caps_lock","left_shift","right_shift",
  "left_ctrl","left_alt","left_gui","space","right_alt","right_ctrl",
  "enter","backspace","delete","insert","home","end","page_up","page_down",
  "up","down","left","right",
  "print_screen","scroll_lock","pause_break",
  "media_play_pause","media_stop","media_prev","media_next","mute","vol_up","vol_down"
"""

import os, json, re
from collections import defaultdict
from config import MAPS_DIR

OUT_JSON = os.path.join(MAPS_DIR, "label_map.json")

# ---------- 유틸 ----------
def norm(s: str) -> str:
    """LED 원시 이름 정규화: 소문자, 앞뒤 공백 제거, 일부 접두/기호 제거, 공백->'_', 영숫자+_만."""
    s = (s or "").strip().lower()
    # 흔한 접두/표기 제거
    s = s.replace("key:", "").replace("key ", "")
    s = s.replace("kbd", "").replace("keyboard", "")
    s = s.replace(" corsair", "")
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ", "_")
    s = s.replace("-", "_")
    s = s.replace(".", "")
    s = s.replace("(", "").replace(")", "")
    s = s.replace("[", "").replace("]", "")
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s

def guess_map_json() -> str:
    cands = [fn for fn in os.listdir(MAPS_DIR) if fn.endswith("_leds.json")]
    if not cands:
        raise FileNotFoundError("maps/ 안에 *_leds.json 이 없습니다. 먼저 export_led_map.py 실행 필요.")
    # 같은 모델 여러 개면 가장 최근 파일 사용
    cands.sort(key=lambda fn: os.path.getmtime(os.path.join(MAPS_DIR, fn)), reverse=True)
    return os.path.join(MAPS_DIR, cands[0])

# ---------- 별칭 사전 ----------
ALIASES = {
    # 최상단/좌상단
    "esc": {"esc", "escape", "esc_key", "escape_key"},
    "grave": {"`", "grave", "backtick", "tilde"},
    # 숫자열(상단)
    "num_1": {"1"}, "num_2": {"2"}, "num_3": {"3"}, "num_4": {"4"}, "num_5": {"5"},
    "num_6": {"6"}, "num_7": {"7"}, "num_8": {"8"}, "num_9": {"9"}, "num_0": {"0"},
    "minus": {"-", "minus", "hyphen"}, "equal": {"=", "equals"},
    "backspace": {"backspace", "bksp"},
    # F열
    "f1": {"f1"}, "f2": {"f2"}, "f3": {"f3"}, "f4": {"f4"}, "f5": {"f5"}, "f6": {"f6"},
    "f7": {"f7"}, "f8": {"f8"}, "f9": {"f9"}, "f10": {"f10"}, "f11": {"f11"}, "f12": {"f12"},
    "print_screen": {"printscreen", "prt_scr", "prtsc", "prtscr"},
    "scroll_lock": {"scrolllock", "scr_lock"},
    "pause_break": {"pause", "break", "pausebreak"},
    # 문자열 1행
    "tab": {"tab"},
    "q": {"q"}, "w": {"w"}, "e": {"e"}, "r": {"r"}, "t": {"t"},
    "y": {"y"}, "u": {"u"}, "i": {"i"}, "o": {"o"}, "p": {"p"},
    "l_bracket": {"[", "lbracket", "left_bracket"},
    "r_bracket": {"]", "rbracket", "right_bracket"},
    "backslash": {"\\", "backslash"},
    # 문자열 2행
    "caps_lock": {"caps", "capslock", "caps_lock"},
    "a": {"a"}, "s": {"s"}, "d": {"d"}, "f": {"f"}, "g": {"g"},
    "h": {"h"}, "j": {"j"}, "k": {"k"}, "l": {"l"},
    "semicolon": {";", "semicolon"}, "quote": {"'", "quote", "apostrophe"},
    "enter": {"enter", "return"},
    # 문자열 3행
    "left_shift": {"lshift", "leftshift", "left_shift"},
    "z": {"z"}, "x": {"x"}, "c": {"c"}, "v": {"v"}, "b": {"b"},
    "n": {"n"}, "m": {"m"},
    "comma": {",", "comma"}, "dot": {".", "period", "dot"},
    "slash": {"/", "slash", "question"},
    "right_shift": {"rshift", "rightshift", "right_shift"},
    # 스페이스열
    "left_ctrl": {"lctrl", "leftctrl", "left_ctrl", "control", "left_control"},
    "left_gui": {"lgui", "leftgui", "left_win", "left_meta", "win", "windows"},
    "left_alt": {"lalt", "leftalt", "left_alt", "alt"},
    "space": {"space", "spacebar"},
    "right_alt": {"ralt", "rightalt", "right_alt", "altgr"},
    "right_gui": {"rgui", "rightgui", "right_win", "right_meta"},
    "menu": {"menu", "application"},
    "right_ctrl": {"rctrl", "rightctrl", "right_ctrl"},
    # 편집/네비
    "insert": {"insert", "ins"},
    "delete": {"delete", "del"},
    "home": {"home"},
    "end": {"end"},
    "page_up": {"pageup", "pgup"},
    "page_down": {"pagedown", "pgdn"},
    "up": {"up", "arrow_up"},
    "down": {"down", "arrow_down"},
    "left": {"left", "arrow_left"},
    "right": {"right", "arrow_right"},
    # 미디어/볼륨(코르세어 상단 다이얼/버튼)
    "media_play_pause": {"playpause", "play_pause", "media_play_pause", "play", "pause", "stop"},
    "media_prev": {"prev", "previous", "media_prev"},
    "media_next": {"next", "media_next"},
    "mute": {"mute"},
    "vol_up": {"volume_up", "vol_up", "volumeup"},
    "vol_down": {"volume_down", "vol_down", "volumedown"},
}

# ---------- 규칙(heuristics) ----------
RE_FKEY = re.compile(r"^f([1-9]|1[0-2])$")
RE_NUMROW = re.compile(r"^[0-9]$")  # 상단 숫자열 (텐키와 구분)
ARROWS = {"arrow_up": "up", "arrow_down": "down", "arrow_left": "left", "arrow_right": "right"}

def heuristic_label_for(name_norm: str):
    """규칙 기반 자동 라벨 추론 (별칭 매칭 실패 시 보조)."""
    # F 키
    m = RE_FKEY.match(name_norm)
    if m:
        return f"f{m.group(1)}"

    # arrow_* -> 방향
    if name_norm in ARROWS:
        return ARROWS[name_norm]

    # 숫자 0~9 -> num_*
    if RE_NUMROW.match(name_norm):
        return f"num_{name_norm}"

    # 흔한 정규화 패턴 대응
    table = {
        "escape": "esc",
        "esc": "esc",
        "back_space": "backspace",
        "caps": "caps_lock",
        "capslock": "caps_lock",
        "lctrl": "left_ctrl",
        "rctrl": "right_ctrl",
        "lalt": "left_alt",
        "ralt": "right_alt",
        "lgui": "left_gui",
        "rgui": "right_gui",
        "leftwin": "left_gui",
        "rightwin": "right_gui",
        "win": "left_gui",
        "windows": "left_gui",
        "return": "enter",
        "bksp": "backspace",
        "pgup": "page_up",
        "pgdn": "page_down",
        "prtscr": "print_screen",
        "prtsc": "print_screen",
        "printscreen": "print_screen",
        "scrolllock": "scroll_lock",
        "pausebreak": "pause_break",
        "playpause": "media_play_pause",
        "play_pause": "media_play_pause",
        "previous": "media_prev",
        "next": "media_next",
        "volumeup": "vol_up",
        "volup": "vol_up",
        "volumedown": "vol_down",
        "voldown": "vol_down",
    }
    if name_norm in table:
        return table[name_norm]

    # 브래킷/세미콜론 등 일부 기호 키
    specials = {
        "lbracket": "l_bracket", "left_bracket": "l_bracket",
        "rbracket": "r_bracket", "right_bracket": "r_bracket",
        "semicolon": "semicolon", "apostrophe": "quote", "quote": "quote",
        "minus": "minus", "equals": "equal", "equal": "equal",
        "period": "dot", "dot": "dot", "comma": "comma",
        "slash": "slash", "backslash": "backslash", "tilde": "grave",
        "question": "slash",
    }
    if name_norm in specials:
        return specials[name_norm]

    return None

# ---------- 메인 ----------
def main():
    json_path = guess_map_json()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    leds = data.get("leds", [])
    name_to_indices = defaultdict(list)
    all_norms = []

    for row in leds:
        idx = row["index"]
        raw = row.get("name_raw", "") or ""
        n = norm(raw)
        all_norms.append((idx, raw, n))
        if n:
            name_to_indices[n].append(idx)

    # 1) 별칭 기반 매핑
    label_to_index = {}
    ambiguous = {}

    def pick_unique(cands, label):
        """후보 여러 개면 ambiguous로 기록, 하나면 채택."""
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            ambiguous[label] = cands
        return None

    for label, alset in ALIASES.items():
        candidates = []
        for alias in alset:
            key = norm(alias)
            if key in name_to_indices:
                for idx in name_to_indices[key]:
                    candidates.append((key, idx))
        chosen = pick_unique(candidates, label)
        if chosen is not None:
            label_to_index[label] = chosen[1]

    # 2) 규칙 기반 보완
    for idx, raw, n in all_norms:
        lab = heuristic_label_for(n)
        if not lab:
            continue
        if lab in label_to_index:
            # 이미 채택된 라벨이면 스킵(충돌 최소화). 필요시 교체 로직 추가 가능.
            continue
        # 같은 라벨 후보가 여러 개일 수 있음 → ambiguous 누적
        if lab not in ambiguous:
            ambiguous[lab] = []
        ambiguous[lab].append((n, idx))

    # 3) 저장
    out = {
        "keyboard": data.get("keyboard"),
        "derived_from": os.path.basename(json_path),
        "label_to_index": label_to_index,  # 확정 매핑 (자동으로 유일하게 잡힌 것들)
        "ambiguous": ambiguous,            # 사람이 한 번 확인해서 결정해주면 됨
        "note": (
            "ambiguous에 나온 라벨은 실제 키를 확인하여 원하는 인덱스를 label_to_index에 직접 써넣으세요. "
            "ALIASES/heuristics를 보강한 뒤 본 스크립트를 다시 돌려도 됩니다."
        ),
    }

    os.makedirs(MAPS_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[OK] 라벨 맵 저장: {OUT_JSON}")
    if ambiguous:
        print("[WARN] 확인 필요한 라벨들(ambiguous) 존재. label_map.json을 열어 정정하세요.")
    else:
        print("[INFO] 모든 라벨이 모호성 없이 매핑되었습니다.")

if __name__ == "__main__":
    main()