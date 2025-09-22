# -*- coding: utf-8 -*-
"""
JSON(…_leds.json)을 직접 읽어 라벨→인덱스 매핑을 즉석에서 구성하고,
라벨로 키 색을 바꾸는 헬퍼.

사용 예:
    from openrgb import OpenRGBClient
    from openrgb.utils import RGBColor
    from keyboard_map import RGBLabelController

    client = OpenRGBClient(address="127.0.0.1", port=6742, name="K70Demo")
    km = RGBLabelController(client, json_path="src/maps/Corsair K70 RGB TKL_leds.json")
    km.set("esc", RGBColor(255,0,0))
"""

import os, json, re, time
from typing import Dict, List, Optional
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from config import MAPS_DIR

def _norm(s: str) -> str:
    """LED 이름 정규화: 소문자, 공백/특수문자 정리."""
    s = (s or "").strip().lower()
    s = s.replace("key:", "").replace("key ", "")
    s = s.replace("keyboard", "").replace("kbd", "")
    s = re.sub(r"\s+", " ", s)           # 다중 공백 하나로
    s = s.strip()
    # 몇몇 기호 보정(원하는 대로 추가 가능)
    s = s.replace("arrow", "arrow")      # placeholder (가독용)
    return s

# 자주 쓰는 라벨 별칭 집합 (필요시 계속 추가하세요)
ALIASES: Dict[str, List[str]] = {
    # 최상단 열
    "esc": ["escape", "esc"],
    "f1": ["f1"], "f2": ["f2"], "f3": ["f3"], "f4": ["f4"],
    "f5": ["f5"], "f6": ["f6"], "f7": ["f7"], "f8": ["f8"],
    "f9": ["f9"], "f10": ["f10"], "f11": ["f11"], "f12": ["f12"],
    "print_screen": ["print screen", "prtsc", "prt sc"],
    "scroll_lock": ["scroll lock"],
    "pause_break": ["pause/break", "pause", "break"],

    # 숫자열 / 기호
    "grave": ["`", "grave", "backtick", "tilde"],
    "1":["1"], "2":["2"], "3":["3"], "4":["4"], "5":["5"],
    "6":["6"], "7":["7"], "8":["8"], "9":["9"], "0":["0"],
    "minus": ["-"], "equal": ["="],
    "backspace": ["backspace"],

    # 편집/이동
    "insert": ["insert"], "home": ["home"], "page_up": ["page up", "page_up"],
    "delete": ["delete"], "end": ["end"], "page_down": ["page down", "page_down"],

    # 탭/대괄호/역슬래시
    "tab": ["tab"],
    "q":["q"], "w":["w"], "e":["e"], "r":["r"], "t":["t"], "y":["y"], "u":["u"], "i":["i"], "o":["o"], "p":["p"],
    "lbracket": ["["], "rbracket": ["]"],
    "backslash": ["\\ (ansi)", "\\", "backslash"],

    # 중간 열
    "caps_lock": ["caps lock", "capslock", "caps"],
    "a":["a"], "s":["s"], "d":["d"], "f":["f"], "g":["g"], "h":["h"], "j":["j"], "k":["k"], "l":["l"],
    "semicolon": [";"], "quote": ["'"],
    "enter": ["enter", "return"],

    # 하단 열
    "left_shift": ["left shift", "lshift"], "z":["z"], "x":["x"], "c":["c"], "v":["v"], "b":["b"], "n":["n"], "m":["m"],
    "comma":[","], "period":["."], "slash":["/"], "right_shift": ["right shift", "rshift"],

    # 스페이스 행
    "left_ctrl": ["left control", "left ctrl", "lctrl"],
    "left_win": ["left windows", "left win", "super"],
    "left_alt": ["left alt", "lalt"],
    "space": ["space", "spacebar"],
    "right_alt": ["right alt", "ralt"],
    "right_fn": ["right fn", "fn"],
    "menu": ["menu", "application"],
    "right_ctrl": ["right control", "right ctrl", "rctrl"],

    # 방향키
    "up": ["up arrow", "up"], "down": ["down arrow", "down"],
    "left": ["left arrow", "left"], "right": ["right arrow", "right"],

    # 상단 기능키/로고/프로필
    "media_stop": ["media stop"],
    "media_prev": ["media previous"],
    "media_play_pause": ["media play/pause", "play/pause", "play pause"],
    "media_next": ["media next"],
    "media_mute": ["media mute"],
    "logo_l": ["logo l"], "logo_r": ["logo r"],
    "profile": ["profile"], "light": ["light"], "lock": ["lock"],
}

class RGBLabelController:
    def __init__(self, client: OpenRGBClient, json_path: Optional[str] = None):
        self.client = client
        self.json_path = json_path or self._default_json_path()
        self.label_to_index = self._build_label_map_from_json(self.json_path)

    def _default_json_path(self) -> str:
        # 기본 경로 추정
        maps_dir = MAPS_DIR
        for fn in os.listdir(maps_dir):
            if fn.endswith("_leds.json"):
                return os.path.join(maps_dir, fn)
        raise FileNotFoundError("maps/ 폴더에 *_leds.json 파일이 없습니다. export_led_map 먼저 실행하세요.")

    def _load_keyboard(self):
        devices = getattr(self.client, "devices", None) or self.client.get_devices()
        for d in devices:
            dtype = getattr(d.type, "name", str(d.type)).lower()
            if dtype == "keyboard":
                return d
        return None

    def _build_label_map_from_json(self, path: str) -> Dict[str, int]:
        """JSON의 name_raw를 정규화하여 ALIASES 라벨과 매칭, 라벨→인덱스 사전 생성."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # name_norm → [indices]
        name_to_indices: Dict[str, List[int]] = {}
        for row in data.get("leds", []):
            idx = int(row["index"])
            nrm = _norm(row.get("name_raw", ""))
            name_to_indices.setdefault(nrm, []).append(idx)

        label_map: Dict[str, int] = {}
        for label, alias_list in ALIASES.items():
            candidates: List[int] = []
            
            # 1. 완전 일치를 먼저 시도
            for a in alias_list:
                key = _norm(a)
                if key in name_to_indices:
                    candidates.extend(name_to_indices[key])

            # 2. 완전 일치하는 후보가 없을 경우에만 부분 일치 시도
            if not candidates:
                for a in alias_list:
                    key = _norm(a)
                    for nrm_name, idxs in name_to_indices.items():
                        if key and key in nrm_name and idxs:
                            candidates.extend(idxs)

            # 중복 제거 + 안정화
            uniq = sorted(set(candidates))
            if len(uniq) == 1:
                label_map[label] = uniq[0]
            # 여러 개면 모호 → 아직은 자동 선택하지 않음(원하면 우선순위 규칙 추가 가능)
        return label_map

    def set(self, label: str, color: RGBColor) -> bool:
        """라벨로 지정한 키에 색을 적용. 성공 시 True."""
        kb = self._load_keyboard()
        if not kb or not kb.leds:
            return False
        try:
            kb.set_mode("direct")
        except Exception:
            pass

        idx = self.label_to_index.get(label.lower())
        if idx is None or not (0 <= idx < len(kb.leds)):
            return False

        try:
            kb.leds[idx].set_color(color)
            time.sleep(0.05)  # 하드웨어/서버 업데이트 대기
            return True
        except Exception:
            return False

    def available_labels(self) -> Dict[str, int]:
        """현재 JSON 기준 자동으로 확정된 라벨 목록(모호성 없는 것만)."""
        return dict(self.label_to_index)