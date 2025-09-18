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

import time
from rgb_controller import connect, disconnect, set_key_color, get_key_color, init_all_keys
from utils.bitgroups import set_group_value, get_group_value, copy_group_value
from utils.keyboard_presets import BYTE_A, BYTE_B
import utils.color_presets as cp

def rgb_routine(label: str):
    # ESC 색상 순환(빨-초-파-끄기)
    for c in [cp.RED, cp.GREEN, cp.BLUE, cp.BLACK]:
        # 실제 장치의 현재색을 읽어 확인
        print(label, "현재색 =", get_key_color(label, fresh=True))
        time.sleep(0.3)
        set_key_color(label, c, debug=True)
        time.sleep(0.6)

def bitgroup_test(n: int):
    time.sleep(0.6)
    set_group_value(BYTE_A, n, on_color=cp.GREEN, off_color=cp.DARK_RED, debug = True)
    # val, bits, on_labels = get_group_value(BYTE_A, debug=True)
    # print("[CHECK] value=", val, "bits(LSB→)=", bits, "on=", on_labels)
    # input()

def main():
    try:
        connect()
        init_all_keys()
        print("[INFO] All keys ready. Press Enter key to start.")
        input()

        bitgroup_test(100)
        input()

        copy_group_value(BYTE_A, BYTE_B,
                 on_color=cp.GREEN,
                 off_color=cp.DARK_RED,
                 debug=True)
        input()
        
    finally:
        init_all_keys()
        disconnect()

if __name__ == "__main__":
    main()