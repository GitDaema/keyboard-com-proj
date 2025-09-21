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
        init_all_keys()
        print("[INFO] All keys ready. Press Enter key to start.")
        input()

        # 데모 2: 라벨/분기 (b를 3까지 증가)
        demo2 = [
            "b = 0",
            "loop:",
            "ADDI b, #1",
            "CMPI b, #3",
            "BNE loop",
            "PRINT b",
            "HALT",
        ]

        demo3 = [
            "a = 5",
            "b = 9",
            "CMP b, a",        # (9-5): Z=0, N=0, C=1(no borrow)
            "BCC neg",         # C=0일 때만 분기 → 여기선 no-branch
            "SUBI b, #1",      # b=8
            "AND b, a",        # b=8 & 5 = 0 → Z=1, N=0
            "BNE cont",        # Z=0일 때만 분기 → 여기선 no-branch
            "PRINT b",         # 0
            "SHL a",           # a=5<<1=10, C=(5의 MSB=0)
            "BMI neg",         # N=1일 때만 분기 → no-branch
            "XOR a, b",        # a=10 ^ 0 = 10 → N=0, Z=0
            "PRINT a",         # 10
            "HALT",
            "neg:",
            "PRINT b",
            "HALT",
            "cont:",
            "PRINT a",
            "HALT",
        ]

        cpu = CPU(debug=True)
        cpu.load_program(demo3)
        cpu.run()
        print("Final Memory:", cpu.mem.vars)
        input()
        
    finally:
        init_all_keys()
        disconnect()

if __name__ == "__main__":
    main()