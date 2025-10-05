# -*- coding: utf-8 -*-
"""
OpenRGB 서버(127.0.0.1:6742)에 연결하여 키보드 LED를 초기화하고,
인터랙티브 모드로 데모 CPU를 실행하는 진입점.

- 실행 전: 장치를 direct 모드로 전환하고 전체 LED를 블랙으로 초기화
- 실행 중: 콘솔에서 Enter(한 스텝) / c(연속) / q(종료) 및 확장 명령으로 제어
- 종료 시: 모든 LED 클리어 후 OpenRGB 연결 해제

필수 사항:
1) OpenRGB를 --server 모드로 실행(이 스크립트가 자동 연결)
2) iCUE / Razer Synapse 등 벤더 소프트웨어는 종료
3) keyboard_map.RGBLabelController 사용(라벨↔LED 인덱스 매핑)
"""

import time
from rgb_controller import connect, disconnect, set_key_color, get_key_color, init_all_keys
from utils.bitgroups import set_group_value, get_group_value, copy_group_value
import utils.keyboard_presets as kp
import utils.color_presets as cp
from sim.cpu import CPU
from utils.run_pause_indicator import run_off
from utils.control_plane import init_default_panel
from sim.data_memory_rgb_visual import DataMemoryRGBVisual
from utils.bus import BusInterface, BusMemory
from utils.ir_indicator import calibrate_ir
from sim.assembler import assemble_program

def rgb_routine(label: str):
    for c in cp.HEX_COLORS.values():
        time.sleep(0.6)
        set_key_color(label, c, debug=True)
        input()

def bitgroup_test(n: int):
    time.sleep(0.6)
    # set_group_value(kp.BYTE_A, n, on_color=cp.GREEN, off_color=cp.DARK_RED, debug = True)
    # val, bits, on_labels = get_group_value(BYTE_A, debug=True)
    # print("[CHECK] value=", val, "bits(LSB->MSB)=", bits, "on=", on_labels)
    # input()

def main():
    try:
        connect()
        time.sleep(0.6)
        init_all_keys()
        # 시작 대기 동안 PAUSE 표시
        try:
            run_off()
        except Exception:
            pass
        try:
            init_default_panel()
        except Exception:
            pass
        print("[INFO] All keys ready. Press Enter to start.")
        input()

        # LED 메모리 I/O 샘플 설정(지연 0~5ms 권장)
        mem_core = DataMemoryRGBVisual(binary_labels=kp.BINARY_COLORS, samples=3, sample_delay_ms=0, debug=False)
        bus = BusInterface(ack_mode="internal", ack_pulse_ms=12, settle_ms=8, ack_timeout_ms=200)
        mem = BusMemory(mem_core, bus, only_variable_keys=True)
        # 1) CPU 구성: ISA 모드 + 인터랙티브 실행(콘솔 입력으로 스텝/제어)
        cpu = CPU(debug=True, mem=mem, interactive=True, use_isa=True)
        # Register CPU as sink for bus-level memory events (watch/break)
        try:
            mem.set_sink(cpu)
        except Exception:
            pass

        # 2) 프로그램: 상태가 “키보드 불빛”에 매핑되도록 작성된 샘플
        #    - IF/THEN/ELSE/END 블록 포함(전처리로 단순화)
        #    - 비교/산술/분기: ==, !=, <, >, <=, >=
        #    - 즉시값 예: #10, #0x1F, #-3 (10진/16진/음수 지원)
        #    - 내부적으로 CMPI/분기(BEQ/BNE/BMI/BPL/BVS/BVC)로 변환
        #    - 변수 이름은 utils/keyboard_presets.py의 VARIABLE_KEYS만 사용
        #      {'q','w','e','r','a','s','d','z','x'}
        program = [
            # 데모 프로그램: 분기/루프 포함 10여 줄
            # 목표:
            # 1) a의 절대값 계산 (IF/THEN/ELSE/END 사용)
            # 2) a가 x와 같은지 비교하여 d에 1/0 기록
            # 3) a가 5가 될 때까지 1씩 감소(분기)

            "start:",
            "a = -7",          # 초기값 설정(MOVI)
            "x = 5",           # 비교 대상
            "s = 0",           # 임시/플래그 용도

            # SHIFT 테스트: s <- a; SHL/SHR 실행(ISA: SHIFT)
            # "s = a",
            # "SHL s",
            # "SHR s",

            # a < 0 이면 a = -a (절대값 만들기)
            "IF a < #0 THEN",
            "    a = 0 - a",   # NEG 동작과 동일(ISA: NEG)
            "END",

            # a == x 이면 d=1, 아니면 d=0
            "IF a == x THEN",
            "    d = 1",
            "ELSE",
            "    d = 0",
            "END",

            # a == 5가 될 때까지 1씩 감소시키는 루프
            "loop:",
            "CMPI a, #5",      # 비교 + 분기(BR rel8)
            "BEQ done",
            "a = a - 1",
            "JMP loop",

            "done:",
            "HALT",
        ]

        # try: # IR 복호 정확도 향상을 위해, 간단 캘리브레이션(선택사항)
        #     calibrate_ir(samples=2, settle_ms=8, debug=False)
        # except Exception:
        #     pass

        # try: # 어셈블 결과 간단 출력(실행은 ISA 기준)
        #     isa = assemble_program(program, debug=False)
        #     print("\n[ASM LIST]")
        #     for i, insn in enumerate(isa):
        #         b0 = ((insn.op4 & 0xF) << 4) | (insn.dst4 & 0xF)
        #         b1 = insn.arg8 & 0xFF
        #         bits16 = f"{((b0<<8)|b1):016b}"
        #         grouped = " ".join(bits16[j:j+4] for j in range(0, 16, 4))
        #         print(f"{i:02d}: {insn.text:<16} | {b0:02X} {b1:02X} | {grouped}")
        # except Exception:
        #     pass

        # 실행
        cpu.load_program(program, debug=True)

        # 모드 선택: run(표시 중심) / run_led(패널 제어 + 기록/서비스)
        try:
            print("[INFO] LED 게이트(run_led) 모드로 실행합니다. 제어는 모두 LED 색으로 트리거됩니다.")
            choice = "2"
        except Exception:
            choice = ""
        # Default to run_led when no choice is entered
        if choice == "":
            choice = "2"

        if True:
            # LED를 스위치로 사용하는 패널 모드
            print("[INFO] LED 패널(run_led) 모드: 콘솔에서 trace/overlay/reset 등 입력 시 LED가 실제로 반영되어 제어됩니다.")
            cpu.cp_enabled = True
            cpu.run_led()
        else:
            # 기존 인터랙티브(run) 모드
            print("[INFO] run 모드: 표시 중심. 콘솔 명령은 실행 제어/LED 표시를 변경합니다.")
            # 인터랙티브: Enter=스텝, c=연속, q=종료 + 확장 명령(cmd)
            cpu.run()

        input()

        # 최종 확인(빠른 요약)
        try:
            va = mem.get('a'); vx = mem.get('x'); vd = mem.get('d'); vs = mem.get('s')
            print(f"[RESULT] a={va} x={vx} d={vd} s={vs}")
        except Exception:
            pass
        
    finally:
        init_all_keys()
        disconnect()

if __name__ == "__main__":
    main()
