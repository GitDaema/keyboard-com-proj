# -*- coding: utf-8 -*-
"""
Keyboard label mapping utilities.

- Loads a JSON map (e.g., data/maps/*_leds.json) exported previously
  and builds a label -> LED index map using simple alias heuristics.
- No direct device control here; backends consume the label map.
"""

import os, json, re
from typing import Dict, List, Optional
from config import MAPS_DIR


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("key:", "").replace("key ", "")
    s = s.replace("keyboard", "").replace("kbd", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# Frequently used label aliases (extend as needed)
ALIASES: Dict[str, List[str]] = {
    # Top-left
    "esc": ["escape", "esc"],
    # F-keys
    "f1": ["f1"], "f2": ["f2"], "f3": ["f3"], "f4": ["f4"],
    "f5": ["f5"], "f6": ["f6"], "f7": ["f7"], "f8": ["f8"],
    "f9": ["f9"], "f10": ["f10"], "f11": ["f11"], "f12": ["f12"],
    "print_screen": ["print screen", "prtsc", "prt sc"],
    "scroll_lock": ["scroll lock"],
    "pause_break": ["pause/break", "pause", "break"],
    # Number row
    "grave": ["`", "grave", "backtick", "tilde"],
    "1":["1"], "2":["2"], "3":["3"], "4":["4"], "5":["5"],
    "6":["6"], "7":["7"], "8":["8"], "9":["9"], "0":["0"],
    "minus": ["-"], "equal": ["="],
    "backspace": ["backspace"],
    # Navigation
    "insert": ["insert"], "home": ["home"], "page_up": ["page up", "page_up"],
    "delete": ["delete"], "end": ["end"], "page_down": ["page down", "page_down"],
    # Letters row 1
    "tab": ["tab"],
    "q":["q"], "w":["w"], "e":["e"], "r":["r"], "t":["t"], "y":["y"], "u":["u"], "i":["i"], "o":["o"], "p":["p"],
    "lbracket": ["["], "rbracket": ["]"],
    "backslash": ["\\ (ansi)", "\\", "backslash"],
    # Letters row 2
    "caps_lock": ["caps lock", "capslock", "caps"],
    "a":["a"], "s":["s"], "d":["d"], "f":["f"], "g":["g"], "h":["h"], "j":["j"], "k":["k"], "l":["l"],
    "semicolon": [";"], "quote": ["'"],
    "enter": ["enter", "return"],
    # Letters row 3
    "left_shift": ["left shift", "lshift"], "z":["z"], "x":["x"], "c":["c"], "v":["v"], "b":["b"], "n":["n"], "m":["m"],
    "comma":[","], "period":["."], "slash":["/"], "right_shift": ["right shift", "rshift"],
    # Space row
    "left_ctrl": ["left control", "left ctrl", "lctrl"],
    "left_win": ["left windows", "left win", "super"],
    "left_alt": ["left alt", "lalt"],
    "space": ["space", "spacebar"],
    "right_alt": ["right alt", "ralt"],
    "right_fn": ["right fn", "fn"],
    "menu": ["menu", "application"],
    "right_ctrl": ["right control", "right ctrl", "rctrl"],
    # Arrows
    "up": ["up arrow", "up"], "down": ["down arrow", "down"],
    "left": ["left arrow", "left"], "right": ["right arrow", "right"],
    # Media / logo
    "media_stop": ["media stop"],
    "media_prev": ["media previous"],
    "media_play_pause": ["media play/pause", "play/pause", "play pause"],
    "media_next": ["media next"],
    "media_mute": ["media mute"],
    "logo_l": ["logo l"], "logo_r": ["logo r"],
    "profile": ["profile"], "light": ["light"], "lock": ["lock"],
}


class RGBLabelController:
    def __init__(self, json_path: Optional[str] = None):
        self.json_path = json_path or self._default_json_path()
        self.label_to_index: Dict[str, int] = self._build_label_map_from_json(self.json_path)

    def _default_json_path(self) -> str:
        maps_dir = MAPS_DIR
        for fn in os.listdir(maps_dir):
            if fn.endswith("_leds.json"):
                return os.path.join(maps_dir, fn)
        raise FileNotFoundError("maps/ directory missing *_leds.json. Run export utility to generate.")

    def _build_label_map_from_json(self, path: str) -> Dict[str, int]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        name_to_indices: Dict[str, List[int]] = {}
        for row in data.get("leds", []):
            try:
                idx = int(row["index"])  # OpenRGB LED index or vendor index depending on source
            except Exception:
                continue
            nrm = _norm(row.get("name_raw", ""))
            name_to_indices.setdefault(nrm, []).append(idx)
        label_map: Dict[str, int] = {}
        for label, alias_list in ALIASES.items():
            candidates: List[int] = []
            for a in alias_list:
                key = _norm(a)
                if key in name_to_indices:
                    candidates.extend(name_to_indices[key])
            if not candidates:
                for a in alias_list:
                    key = _norm(a)
                    for nrm_name, idxs in name_to_indices.items():
                        if key and key in nrm_name and idxs:
                            candidates.extend(idxs)
            uniq = sorted(set(candidates))
            if len(uniq) == 1:
                label_map[label] = uniq[0]
        return label_map

    def available_labels(self) -> Dict[str, int]:
        return dict(self.label_to_index)