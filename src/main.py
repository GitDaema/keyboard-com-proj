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
import utils.keyboard_presets as kp
import utils.color_presets as cp
from sim.cpu import CPU
from sim.data_memory_rgb_visual import DataMemoryRGBVisual

def rgb_routine(label: str):
    for c in cp.HEX_COLORS.values():
        time.sleep(0.6)
        set_key_color(label, c, debug=True)
        input()

def bitgroup_test(n: int):
    time.sleep(0.6)
    # set_group_value(kp.BYTE_A, n, on_color=cp.GREEN, off_color=cp.DARK_RED, debug = True)
    # val, bits, on_labels = get_group_value(BYTE_A, debug=True)
    # print("[CHECK] value=", val, "bits(LSB→)=", bits, "on=", on_labels)
    # input()

def main():
    try:
        connect()
        time.sleep(0.6)
        init_all_keys()
        print("[INFO] All keys ready. Press Enter key to start.")
        input()

        mem=DataMemoryRGBVisual(binary_labels=kp.BINARY_COLORS)
        # 1) CPU 생성 시 LED 메모리 장착
        cpu = CPU(debug=True, mem=mem, interactive=True)

        # 2) 프로그램: 상태가 전부 “불빛”에 저장됨
        program = [
            "start:",
            "a = 5",
            "b = 5",
            "CMP a, b",
            "BEQ equal_case",
            "JMP fail",
            "equal_case:",
            "b = -7",
            "CMP b, a",
            "BMI negative_case",
            "JMP fail",
            "negative_case:",
            "CMP a, #2",
            "BPL positive_case",
            "JMP fail",
            "positive_case:",
            "CMP b, #0",
            "BNE done",
            "JMP fail",
            "done:",
            "HALT",
            "fail:",
            "HALT"
        ]

        cpu.load_program(program)
        cpu.run()
        
        input()
        
    finally:
        init_all_keys()
        disconnect()

if __name__ == "__main__":
    main()