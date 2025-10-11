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
import os
import sys

# Prefer local rgb_controller; fall back to project-root dump_rgb_controller if needed
try:
    import rgb_controller as rc  # from src/
    if not hasattr(rc, "connect"):
        raise AttributeError("rgb_controller.connect missing")
except Exception:
    try:
        ROOT = os.path.dirname(os.path.dirname(__file__))
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        import importlib
        rc = importlib.import_module('dump_rgb_controller')  # fallback copy
    except Exception as _ex:
        # Defer error until main() runs to show a clearer message
        rc = None  # type: ignore
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
        rc.set_key_color(label, c, debug=True)
        input()

def bitgroup_test(n: int):
    time.sleep(0.6)
    # set_group_value(kp.BYTE_A, n, on_color=cp.GREEN, off_color=cp.DARK_RED, debug = True)
    # val, bits, on_labels = get_group_value(BYTE_A, debug=True)
    # print("[CHECK] value=", val, "bits(LSB->MSB)=", bits, "on=", on_labels)
    # input()

def main():
    try:
        if rc is None:
            raise RuntimeError("rgb_controller 모듈을 불러오지 못했습니다")
        try:
            rc.connect()
        except Exception as ex:
            try:
                print("[ERROR] OpenRGB 연결 실패:", ex)
                print("[HINT] OpenRGB UI에서 SDK Server를 Start하고, 관리자 권한 실행을 시도해 보세요.")
            except Exception:
                pass
            try:
                input("Enter 키를 누르면 종료합니다.")
            except Exception:
                pass
            return
        time.sleep(0.6)
        rc.init_all_keys()
        # 시작 대기 동안 PAUSE 표시
        try:
            run_off()
        except Exception:
            pass
        try:
            init_default_panel()
        except Exception:
            pass
        # [TEMP] Auto-benchmark mode enabled by default (no prompt)
        # print("[INFO] All keys ready. Press Enter to start.")
        # input()

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
            "s = a",
            "SHL s",
            "SHR s",

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

        # --- BENCH: type 'bench fast' or 'bench normal' then Enter to measure ---
        bench = False
        bench_fast = False
        try:
            print("[BENCH] 입력: 'bench fast' | 'bench normal' | Enter=skip > ", end="", flush=True)
            sel = input().strip().lower()
            if sel.startswith("bench"):
                bench = True
                bench_fast = ("fast" in sel)
        except Exception:
            bench = False
            bench_fast = False
        if bench:
            try:
                if bench_fast:
                    # Apply FAST (single high-speed preset) with visual group-atomic commits
                    cpu._apply_speed_preset("FAST_SAFE")
                    print("[BENCH] preset=FAST (FAST_SAFE)")
                else:
                    # Ensure fast-specific toggles are off
                    try:
                        from rgb_controller import set_group_atomic
                        set_group_atomic(False)
                    except Exception:
                        pass
                    print("[BENCH] preset=NORMAL")
            except Exception:
                pass
            try:
                cpu.cp_enabled = True
                cpu._cmd_q.put("run")  # continuous run
            except Exception:
                pass
            t0 = time.perf_counter()
            cpu.run_led()
            t1 = time.perf_counter()
            elapsed_s = max(0.0, float(t1 - t0))
            total_ms = elapsed_s * 1000.0
            try:
                insns = len(getattr(cpu, "_isa", []) or [])
            except Exception:
                insns = 0
            if insns > 0 and elapsed_s > 0:
                ips = insns / elapsed_s
                print(f"[BENCH] insns={insns} total_ms={total_ms:.1f} ips={ips:.1f}")
            else:
                print(f"[BENCH] total_ms={total_ms:.1f}")
            return

        # --- DEMO: Force bus ACK failure to verify FAULT latch ---
        do_demo = False
        try:
            # Environment override: set ACK_FAIL_DEMO=1 to auto-run
            do_demo = str(os.environ.get("ACK_FAIL_DEMO", "")).strip().lower() in ("1", "y", "yes", "true")
        except Exception:
            do_demo = False
        # Interactive demo prompt disabled for non-interactive safety
        if False and not do_demo:
            try:
                print("[DEMO] 버스 ACK 실패 데모를 실행할까요? (y/N)")
                ans = input().strip().lower()
                do_demo = ans in ("y", "yes")
            except Exception:
                do_demo = False

        if do_demo:
            try:
                # Make ACK wait for an external source that never arrives
                bus.ack_mode = "external"
                bus.ack_timeout_ms = 80  # quick timeout for demo
                print("[DEMO] ack_mode=external, ack_timeout_ms=80 -> 의도적으로 ACK를 받지 못하게 합니다.")
            except Exception:
                pass
            try:
                # Auto-run so the first variable write triggers the bus failure immediately
                cpu.cp_enabled = True
                cpu._cmd_q.put("run")  # continuous run
                print("[DEMO] 자동으로 run을 트리거합니다. 곧 ACK 실패 → FAULT로 정지해야 합니다.")
            except Exception:
                pass
            try:
                cpu.run_led()
            except Exception:
                # Any unexpected exception: keep the panel state for inspection
                pass
            try:
                print("[DEMO] 데모 종료. grave 키가 빨강(FAULT/HALT)으로 표시되는지 확인하세요. Enter를 누르면 종료합니다.")
                input()
            except Exception:
                pass
            return

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
        try:
            if rc is not None:
                try:
                    # Best-effort: clear all keys only when connected
                    if getattr(rc, 'is_connected', None) and rc.is_connected():
                        rc.init_all_keys()
                except Exception:
                    # Last-ditch: still try to clear without check
                    try:
                        rc.init_all_keys()
                    except Exception:
                        pass
                try:
                    rc.disconnect()
                except Exception:
                    pass
        except Exception:
            pass

if __name__ == "__main__":
    main()
