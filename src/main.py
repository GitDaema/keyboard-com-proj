# -*- coding: utf-8 -*-
"""
OpenRGB 서버(127.0.0.1:6742)에 연결해 ESC 키만 제어하는 예제.
- 첫 실행 시 인덱스/라벨 흔들림 방지를 위해: direct 모드 전환 → 동기화 → 전체 올블랙 초기화
- 종료 시 세션 정리(client.disconnect)

필수:
1) OpenRGB가 --server로 떠 있어야 함(런 스크립트가 자동 처리)
2) iCUE / Razer Synapse 등은 종료
3) keyboard_map.RGBLabelController 사용 (라벨 → LED 인덱스 매핑)
"""

import os
import time
from openrgb.utils import RGBColor
from rgb_controller import connect, disconnect, set_key_color, get_key_color, init_all_keys
from utils.bitgroups import set_group_value
from utils.presets import BYTE_A

def rgb_routine(label: str):
    # ESC 색상 순환(빨-초-파-끄기)
    for c in [RGBColor(255,0,0), RGBColor(0,255,0), RGBColor(0,0,255), RGBColor(0,0,0)]:
        # 실제 장치의 현재색을 읽어 확인
        print(label, "현재색 =", get_key_color(label, fresh=True))
        time.sleep(0.3)
        set_key_color(label, c, debug=True)
        time.sleep(0.6)

def bitgroup_test(n: int):
    green = RGBColor(0,255,0)
    dark_green = RGBColor(0, 50, 0)
    time.sleep(0.6)
    set_group_value(BYTE_A, n, on_color=green, off_color=dark_green, lsb_first=False)
    input()

def main():
    try:
        connect()
        init_all_keys()

        bitgroup_test(0)
        bitgroup_test(1)
        bitgroup_test(127)
        bitgroup_test(255)
        
    finally:
        init_all_keys()
        disconnect()

if __name__ == "__main__":
    main()