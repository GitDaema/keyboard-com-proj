# sim/cpu.py
from typing import Dict, Any, List, Tuple, Optional
import time
import threading
from queue import Queue, Empty

from utils.keyboard_presets import FLAG_LABELS, BINARY_COLORS
import utils.color_presets as cp
from rgb_controller import set_key_color
from utils.stage_indicator import post_stage, clear_stages
from utils.ir_indicator import update_from_decoded, clear_ir, encode_from_source_line_fixed, set_ir, read_ir
from utils.ir_indicator import calibrate_ir
from utils.run_pause_indicator import run_on, run_off
from utils.pc_indicator import update_pc, clear_pc
from utils.control_plane import (
    set_run_state,
    set_esc_state,
    set_step_mode,
    set_trace_state,
    set_overlay_mode,
)
from utils.control_plane import (
    poll as cp_poll,
    maybe_run_service as cp_service,
    ControlStates,
)

from sim.pc import PC
from sim.ir import IR
from sim.data_memory_rgb_visual import DataMemoryRGBVisual
from sim.program_memory import ProgramMemory
from sim.parser import parse_line, preprocess_program
from sim.assembler import assemble_program, AsmInsn, OPCODES, BR_COND, EXT_TYPE_IMM

from utils.bit_lut import (
    add8_via_lut, sub8_via_lut, and8_via_lut, or8_via_lut, xor8_via_lut,
    shl8_via_lut, shr8_via_lut
)
from utils.keyboard_presets import SRC1, SRC2, RES
from utils.keyboard_presets import VARIABLE_KEYS, BUS_ADDR_VALID, BUS_RD, BUS_WR, BUS_ACK


"""
# =========================
# CPU/Parser 紐낅졊???뺣━ (signed 踰꾩쟾)
# =========================
#
# ??湲곕낯 洹쒖튃
# - 紐⑤뱺 怨꾩궛? signed 8鍮꾪듃(-128..127)濡??숈옉.
# - ?뚮옒洹?
#     Z (Zero)      : 寃곌낵媛 0?대㈃ 1
#     N (Negative)  : 寃곌낵媛 ?뚯닔(遺?몃퉬??1)硫?1
#     V (oVerflow)  : signed overflow 諛쒖깮 ??1 (ADD/SHL/SUB/CMP ??
# - PC??"?ㅼ쓬 紐낅졊???꾩튂". 蹂댄넻 ??移몄뵫 利앷??섏?留?
#   ?먰봽/遺꾧린(JMP, BEQ ??媛 ?ㅽ뻾?섎㈃ 吏곸젒 諛붾?
# - 利됱떆媛??쒓린: #10, #0x1F, #-3 ??紐⑤몢 ?덉슜.
#
# ??湲곕낯 紐낅졊??
# - NOP / LABEL / HALT / PRINT (?숈씪)
#
# ??媛??ｊ린 / ?뷀븯湲?/ 鍮쇨린
# - MOVI dst, #imm         ; dst ??imm (signed 踰붿쐞濡??섑븨 ???
# - MOV  dst, src          ; dst ??src
# - ADDI dst, #imm         ; dst ??dst + imm (Z/N/V 媛깆떊)
# - ADD  dst, src          ; dst ??dst + src (Z/N/V 媛깆떊)
# - SUBI dst, #imm         ; dst ??dst - imm (Z/N/V 媛깆떊)
# - SUB  dst, src          ; dst ??dst - src (Z/N/V 媛깆떊)
#
# ??鍮꾪듃 ?곗궛 (Z/N 媛깆떊, V=0)
# - AND/OR/XOR
#
# ???쒗봽??
# - SHL dst                ; ?곗닠???섎????쇱そ ?쒗봽??理쒖긽??鍮꾪듃 蹂?붾줈 V ?먮떒)
# - SHR dst                ; ?곗닠 ?쒗봽??ASR, 遺???좎?). V=0
#
# ??鍮꾧탳 / 遺꾧린 (signed)
# - CMP a, b               ; a-b??signed 寃곌낵 湲곕컲?쇰줈 Z/N/V 媛깆떊(寃곌낵??踰꾨┝)
# - CMPI a, #imm
#
# - JMP label              ; 臾댁“嫄?遺꾧린
# - BEQ/BNE                ; Z=1 / Z=0
# - BMI/BPL                ; N=1 / N=0
# - BVS/BVC                ; V=1 / V=0
#   (?섏쐞?명솚) BCS/BCC     ; V=1 / V=0 濡??댁꽍
"""

def _wrap_s8(x: int) -> int:
    return ((int(x) + 128) & 0xFF) - 128

def _to_u8(x: int) -> int:
    return int(x) & 0xFF

def _sign_bit(x: int) -> int:
    return 1 if (_to_u8(x) & 0x80) else 0

def _set_zn_from_val(flags: Dict[str, int], v: int) -> None:
    flags["Z"] = 1 if v == 0 else 0
    flags["N"] = 1 if v < 0 else 0

class CPU:
    def __init__(self, *, debug: bool = False, mem=None, interactive: bool = False, use_isa: bool = True) -> None:
        self.pc = PC()
        self.ir = IR()
        self.mem = mem if mem is not None else DataMemoryRGBVisual(binary_labels=BINARY_COLORS)
        self.prog = ProgramMemory()
        self.halted = False
        self.debug = debug

        # ?뚮옒洹? Zero / Negative / oVerflow / Carry
        self.flags: Dict[str, int] = {"Z": 0, "N": 0, "V": 0, "C": 0}
        self._pc_overridden: bool = False

        self.interactive = interactive                         # ???ㅽ뀦 ?ㅽ뻾 ?뚮옒洹?        self._continue_run = False                             # ??'c' ?낅젰 ??怨꾩냽 吏꾪뻾
        self.use_isa = use_isa                                 # ??ISA 紐⑤뱶 ?ъ슜 ?щ?

        # ISA instruction stream (when use_isa=True)
        self._isa: list[AsmInsn] = []
        # Control-plane integration (LED-gated run loop)
        # 湲곕낯媛?False: ?명꽣?숉떚釉?紐⑤뱶?먯꽌 肄섏넄 ?낅젰 ?곗꽑
        self.cp_enabled: bool = False
        self._trace_log: list[Dict[str, Any]] = []
        # Track if a reset was requested during a step so we don't overwrite PC later in the same step
        self._reset_pending: bool = False
        # Break/Watch/Bank config (driven by LED control-plane)
        self._break_mode: str = "NONE"   # NONE | BRANCH | WWRITE
        self._watch_mode: str = "NONE"   # NONE | READ | WRITE
        self._space_mode: str = "DATA0"  # DATA0 | DATA1 | PROG | IO
        # Background command reader for interactive mode
        self._cmd_q: Queue[str] = Queue()
        self._cmd_thread = None  # type: ignore[assignment]
        # LED control-plane continuous run state (applies in run_led mode)
        self._cp_continuous_run: bool = False
        self._cp_single_step: bool = False
        # Per-step write detection for one-shot MARK consumption
        self._write_hit_in_step: bool = False
        # One-shot trace marker (caps MARK) state
        self._trace_mark_armed: bool = False
        # Keep original and expanded source to allow runtime ISA<->micro switching
        self._source_lines: List[str] = []
        self._expanded_lines: List[str] = []
        # PC mapping tables between micro-line index and ISA PC index
        self._map_micro_to_isa: List[int] = []
        self._map_isa_to_micro: List[int] = []

    def _build_pc_maps(self) -> None:
        """Build mappings between micro "executable" lines (labels removed)
        and ISA PCs so that switching modes preserves the current position.

        We must align micro indices with ProgramMemory.exec_lines indexing
        (label-only lines don't consume addresses). To do this, compact the
        expanded source by skipping label-only lines when building maps.

        - For each executable micro line j (corresponding expanded index i),
          compute how many ISA instructions it emits (k).
        - map_micro_to_isa[j] = cumulative ISA index at start of that line
          (or -1 if k==0)
        - map_isa_to_micro[pc] = executable micro line index j that produced
          this ISA instruction
        """
        # Build list of expanded indices that are executable (not label-only)
        exec_indices: list[int] = []
        for i, raw in enumerate(self._expanded_lines):
            s = (raw or "").strip()
            if s.endswith(":") and (":" not in s[:-1]):
                # label-only line; does not consume an executable micro PC
                continue
            exec_indices.append(i)

        self._map_micro_to_isa = [-1] * len(exec_indices)
        self._map_isa_to_micro = []
        pc_acc = 0
        for j, i in enumerate(exec_indices):
            line = self._expanded_lines[i]
            try:
                isa_chunk = assemble_program([line], debug=False)
            except Exception:
                isa_chunk = []
            k = len(isa_chunk)
            if k > 0:
                self._map_micro_to_isa[j] = pc_acc
                for _ in range(k):
                    self._map_isa_to_micro.append(j)
                pc_acc += k
        # If overall ISA size differs (e.g., multi-line expansion nuances), pad conservatively
        try:
            isa_len = len(self._isa)
        except Exception:
            isa_len = len(self._map_isa_to_micro)
        while len(self._map_isa_to_micro) < isa_len:
            # Fallback to last executable line if any, else 0
            fallback = max(0, len(exec_indices) - 1)
            self._map_isa_to_micro.append(fallback)

    def _enter_micro_mode(self) -> None:
        """Switch to micro-line stepping at runtime.
        Ensures program memory is populated and PC is valid.
        """
        prev_isa = self.use_isa
        try:
            need_load = False
            try:
                # ProgramMemory may expose size(); otherwise probe fetch(0)
                need_load = (self.prog.fetch(0) is None)
            except Exception:
                need_load = True
            if need_load and self._expanded_lines:
                self.prog.load_program(self._expanded_lines)
        except Exception:
            pass
        # Map current ISA PC to nearest micro line if coming from ISA
        try:
            if prev_isa and self._map_isa_to_micro:
                cur = int(self.pc.value)
                cur = max(0, min(cur, len(self._map_isa_to_micro) - 1))
                self.pc.value = int(self._map_isa_to_micro[cur])
                self.halted = False
            else:
                # Clamp to executable micro lines (labels removed)
                try:
                    n_exec = self.prog.size()
                except Exception:
                    # Fallback: estimate from expanded by excluding label-only lines
                    n_exec = 0
                    for raw in self._expanded_lines:
                        s = (raw or "").strip()
                        if s.endswith(":") and (":" not in s[:-1]):
                            continue
                        n_exec += 1
                if n_exec > 0 and (self.pc.value < 0 or self.pc.value >= n_exec):
                    self.pc.value = 0
                    self.halted = False
        except Exception:
            pass
        # finally switch mode flag
        self.use_isa = False

    def _enter_instr_mode(self) -> None:
        """Switch to ISA stepping at runtime; ensure ISA stream exists and PC valid."""
        prev_isa = self.use_isa
        try:
            if not self._isa and self._source_lines:
                self._isa = assemble_program(self._source_lines, debug=False)
        except Exception:
            pass
        # Map current micro line to nearest ISA PC when coming from micro
        try:
            if (not prev_isa) and self._map_micro_to_isa:
                ml = int(self.pc.value)
                # If this line emitted no ISA, scan backward then forward for nearest mapped line
                target = -1
                if 0 <= ml < len(self._map_micro_to_isa):
                    target = self._map_micro_to_isa[ml]
                if target is None or target < 0:
                    j = ml - 1
                    while j >= 0 and self._map_micro_to_isa[j] < 0:
                        j -= 1
                    if j >= 0:
                        target = self._map_micro_to_isa[j]
                if (target is None or target < 0) and len(self._expanded_lines) > 0:
                    j = ml + 1
                    while j < len(self._map_micro_to_isa) and self._map_micro_to_isa[j] < 0:
                        j += 1
                    if j < len(self._map_micro_to_isa):
                        target = self._map_micro_to_isa[j]
                if target is None or target < 0:
                    target = 0
                self.pc.value = int(target)
                self.halted = False
            else:
                n = len(self._isa)
                if n > 0 and (self.pc.value < 0 or self.pc.value >= n):
                    self.pc.value = 0
                    self.halted = False
        except Exception:
            pass
        # finally switch mode flag
        self.use_isa = True

    def _maybe_watch_prog_event(self, kind: str) -> None:
        """Apply watch/break semantics for program space (IR/PC) when overlay=IRPC.
        kind: 'IR_WRITE' | 'IR_READ' | 'PC_WRITE'
        """
        try:
            if self._space_mode != "PROG":
                return
            if self._watch_mode == "READ" and kind in ("IR_READ",):
                self._println(f"[WATCH] PROG {kind.lower()} -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            if self._watch_mode == "WRITE" and kind in ("IR_WRITE", "PC_WRITE"):
                self._println(f"[WATCH] PROG {kind.lower()} -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            if self._break_mode == "WWRITE" and kind in ("IR_WRITE", "PC_WRITE"):
                self._println(f"[BRK]    PROG {kind.lower()} -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- ?몃? API ----------
    def load_program(self, lines: List[str], *, debug: bool | None = None) -> None:
        dbg = self.debug if debug is None else bool(debug)
        # Preserve originals for runtime switching
        try:
            self._source_lines = list(lines)
        except Exception:
            self._source_lines = lines
        try:
            self._expanded_lines = preprocess_program(lines)
        except Exception:
            self._expanded_lines = list(lines)
        if self.use_isa:
            # Assemble into ISA stream (2-byte per insn)
            try:
                self._isa = assemble_program(lines, debug=dbg)
            except Exception as ex:
                print(f"[ASM] Error: {ex}. Falling back to raw lines.")
                self._isa = []
        else:
            try:
                expanded = preprocess_program(lines)
            except Exception:
                expanded = lines
            self.prog.load_program(expanded)
        # Rebuild PC mapping after both representations updated
        try:
            self._build_pc_maps()
        except Exception:
            pass
        self.pc.reset()
        self.halted = False
        self.ir.clear()
        self.flags["Z"] = 0
        self.flags["N"] = 0
        self.flags["V"] = 0
        self.flags["C"] = 0

        # 珥덇린 ?뚮옒洹??곹깭瑜?LED??1??諛섏쁺(Off ?곹깭?쇰룄 諛붾줈 蹂댁씠寃?
        try:
            self._sync_flag_leds()
        except Exception:
            pass

        # Clear control-stage indicators at program load
        try:
            clear_stages()
        except Exception:
            pass

        # Clear IR visualization
        try:
            clear_ir()
        except Exception:
            pass

        self._continue_run = False

        # Initialize PC indicator to OFF (dark gray)
        try:
            clear_pc()
        except Exception:
            pass

    def step(self) -> bool:
        if self.halted:
            self._on_halt()
            return False

        if self.use_isa:
            return self._step_isa()
        else:
            return self._step_micro()

    def _step_micro(self) -> bool:
        # Original micro-op per line execution (legacy)
        # Capture PC at the start of the step for accurate logging
        start_pc = self.pc.value
        line = self.prog.fetch(self.pc.value)
        if line is None:
            self.halted = True
            self._on_halt()
            return False
        self._pc_overridden = False
        self.ir.raw = line
        self._on_fetch(line)
        ops = parse_line(line)
        for op, args in ops:
            try:
                post_stage("FETCH")
            except Exception:
                pass
            self.ir.decoded = (op, args)
            self._on_decode((op, args))
            self._println(
                f"PC:{self.pc.value:02d} | OP:{op:<4} | ARGS:{args} "
                f"| Z:{self.flags['Z']} N:{self.flags['N']} V:{self.flags['V']}"
            )
            changes = self._exec_one(op, args)
            self._on_writeback(changes)
            self._sync_flag_leds()
            self._maybe_pause()
            # If a reset happened during pause, stop here to avoid overwriting PC
            if getattr(self, "_reset_pending", False):
                try:
                    self._on_pc_advance(start_pc, self.pc.value)
                except Exception:
                    pass
                self._reset_pending = False
                self.ir.clear()
                return not self.halted
            if self.halted or self._pc_overridden:
                break
        if not self._pc_overridden:
            self.pc.increment(1)
            self._on_pc_advance(start_pc, self.pc.value)
        else:
            self._on_pc_advance(start_pc, self.pc.value)
        self.ir.clear()
        # Break on control-flow events when configured (BRANCH mode, IR/PC space)
        try:
            if self._break_mode == "BRANCH" and self._space_mode in ("PROG", "DATA0", "DATA1"):
                # A simple heuristic: halt when op is any branch/JMP or CMP was executed in this step
                dec = getattr(self.ir, "decoded", None)
                if dec is not None:
                    op = str(dec[0]).upper()
                    if op in ("JMP", "BEQ", "BNE", "BMI", "BPL", "BVS", "BVC", "BCS", "BCC", "CMP", "CMPI"):
                        # Pause instead of halt on branch/compare event
                        self._println(f"[BRK]    {op} event -> PAUSE")
                        try:
                            run_off(); set_run_state("PAUSE")
                        except Exception:
                            pass
        except Exception:
            pass
        return not self.halted

    def _step_isa(self) -> bool:
        start_pc = self.pc.value
        if start_pc < 0 or start_pc >= len(self._isa):
            self.halted = True
            self._on_halt()
            return False
        cur_pc = start_pc
        ext_imm_pending = False
        ext_imm_val = 0
        # Consume any prefix frames (e.g., EXTI) before executing the real op
        while True:
            insn = self._isa[cur_pc]
            # FETCH stage + IR update (write)
            try:
                post_stage("FETCH")
            except Exception:
                pass
            try:
                update_pc(cur_pc)
            except Exception:
                pass
            try:
                set_ir(insn.op4, insn.dst4, insn.arg8)
            except Exception:
                pass
            # Watch IR write in PROG overlay
            try:
                self._maybe_watch_prog_event("IR_WRITE")
            except Exception:
                pass
            self._println(f"[FETCH] PC={cur_pc:02d}  insn='{insn.text}' | op={insn.op4:X} dst={insn.dst4:X} arg={insn.arg8:02X}")

            # Guard: assembler fallback NOP for unsupported/garbled source lines
            # Text "NOP ; <src>" indicates an invalid line was lowered to NOP.
            try:
                if insn.op4 == OPCODES["NOP"] and isinstance(insn.text, str) and insn.text.upper().startswith("NOP ;"):
                    # Treat as a hardware fault rather than silently skipping
                    self._trap_fault("ISA invalid line", ValueError(insn.text))
                    return False
            except Exception:
                # Do not crash if trap handler raises; still halt
                self.halted = True
                return False

            # DECODE stage (read IR back)
            try:
                post_stage("DECODE")
            except Exception:
                pass
            op4, dst4, arg8 = read_ir(samples=3, use_calibration=True, debug=False)
            # Watch IR read in PROG overlay
            try:
                self._maybe_watch_prog_event("IR_READ")
            except Exception:
                pass
            self._println(f"[DECODE] op={op4:X} dst={dst4:X} arg={arg8:02X}")

            # EXT prefix: op nibble matches NOP but with DST marking type
            if op4 == OPCODES.get("EXT", 0x0) and (dst4 & 0xF) == (EXT_TYPE_IMM & 0xF):
                # Latch immediate for next op
                ext_imm_pending = True
                ext_imm_val = int(arg8 if arg8 < 128 else arg8 - 256)
                self._on_execute(f"EXTI #{ext_imm_val}")
                # WRITEBACK (no changes)
                try:
                    post_stage("WRITEBACK")
                except Exception:
                    pass
                self._println("[WB]     (no changes)")
                cur_pc += 1
                continue
            break

        # EXECUTE
        taken = False
        next_pc = cur_pc + 1
        ch: Dict[str, int] = {}
        try:
            post_stage("EXECUTE")
        except Exception:
            pass

        def var_name(v4: int) -> str:
            from utils.keyboard_presets import ID_TO_VAR
            return ID_TO_VAR.get(int(v4) & 0xF, 'q')

        # Helper: write group from signed int
        def _write_u8_to_group(grp: str, u8: int):
            labels = self._group_labels(grp)
            u8 &= 0xFF
            width = len(labels)
            for i in range(width):
                bit = (u8 >> i) & 1
                lab = labels[width - 1 - i]
                self.mem.set(lab, bit)

        def _read_res_s8() -> int:
            u8 = self._read_u8_from_group("RES")
            return u8 if u8 < 128 else u8 - 256

        # Execute by opcode
        if op4 == OPCODES["NOP"]:
            self._on_execute("NOP (ISA)")
        elif op4 == OPCODES["HALT"]:
            self._on_execute("HALT (ISA)")
            self.halted = True
        elif op4 == OPCODES["MOVI"]:
            dst = var_name(dst4)
            imm = int(arg8 if arg8 < 128 else arg8 - 256)
            _write_u8_to_group("SRC1", arg8)
            self._on_execute(f"MOVI {dst}, #{imm}")
            # COPY ??PACK
            ch = {}
            # Directly set via PACK pipeline
            self._clear_group("RES")
            self._write_u8_to_group("RES", arg8)
            v = _read_res_s8()
            self.mem.set(dst, v)
            ch[dst] = v
        elif op4 == OPCODES["MOV"]:
            dst = var_name(dst4)
            src = var_name(arg8 & 0xF)
            v = self.mem.get(src)
            self._on_execute(f"MOV {dst},{src} ; {dst}={v}")
            self.mem.set(dst, v)
            ch = {dst: v}
        elif op4 in (OPCODES["ADD"], OPCODES["ADDI"], OPCODES["SUB"], OPCODES["SUBI"], OPCODES["AND"], OPCODES["OR"], OPCODES["XOR"], OPCODES["CMP"], OPCODES["SHIFT"], OPCODES["NEG"]):
            # Map to existing micro-ops via groups/LUTs
            # Prepare operands into groups as needed
            is_cmpi = (op4 == OPCODES["CMP"]) and ext_imm_pending
            if (op4 in (OPCODES["ADDI"], OPCODES["SUBI"])) or is_cmpi:
                dst = var_name(dst4)
                a = self.mem.get(dst)
                b = int(ext_imm_val if is_cmpi else (arg8 if arg8 < 128 else arg8 - 256))
                self._write_u8_to_group("SRC1", _to_u8(a))
                self._write_u8_to_group("SRC2", _to_u8(b))
            elif op4 in (OPCODES["SHIFT"],):
                dst = var_name(dst4)
                a = self.mem.get(dst)
                self._write_u8_to_group("SRC1", _to_u8(a))
            elif op4 == OPCODES["NEG"]:
                dst = var_name(dst4)
                a = self.mem.get(dst)
                # Prepare groups for 0 - a
                self._write_u8_to_group("SRC1", 0)
                self._write_u8_to_group("SRC2", _to_u8(a))
            else:
                dst = var_name(dst4)
                src = var_name(arg8 & 0xF)
                a = self.mem.get(dst)
                b = self.mem.get(src)
                self._write_u8_to_group("SRC1", _to_u8(a))
                self._write_u8_to_group("SRC2", _to_u8(b))

            # Execute using existing helpers
            if op4 == OPCODES["ADDI"]:
                add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_same_sign = _sign_bit(a) == _sign_bit(b)
                self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"ADDI {dst}, #{b}")
                ch = {dst: v}
            elif op4 == OPCODES["ADD"]:
                add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_same_sign = _sign_bit(a) == _sign_bit(b)
                self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"ADD {dst}, {src}")
                ch = {dst: v}
            elif op4 == OPCODES["SUBI"]:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"SUBI {dst}, #{b}")
                ch = {dst: v}
            elif op4 == OPCODES["SUB"]:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"SUB {dst}, {src}")
                ch = {dst: v}
            elif op4 in (OPCODES["AND"], OPCODES["OR"], OPCODES["XOR"]):
                lut = {OPCODES["AND"]: and8_via_lut, OPCODES["OR"]: or8_via_lut, OPCODES["XOR"]: xor8_via_lut}[op4]
                lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                self.flags["V"] = 0
                _set_zn_from_val(self.flags, v)
                name = {OPCODES["AND"]:"AND", OPCODES["OR"]:"OR", OPCODES["XOR"]:"XOR"}[op4]
                self._on_execute(f"{name} {dst}, {src}")
                ch = {dst: v}
            elif op4 == OPCODES["CMP"] and not is_cmpi:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"CMP {dst}, {src}")
            elif op4 == OPCODES["CMP"] and is_cmpi:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"CMPI {dst}, #{b}")
            elif op4 == OPCODES["SHIFT"]:
                # ARG bit0 decides direction
                if (arg8 & 0x01) == 0:
                    # SHL
                    shl8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
                    res_u8 = self._read_u8_from_group("RES")
                    v = res_u8 if res_u8 < 128 else res_u8 - 256
                    self.flags["C"] = 1 if (_to_u8(a) & 0x80) else 0
                    ov = 1 if (_sign_bit(a) != _sign_bit(v)) else 0
                    self.mem.set(dst, v)
                    self.flags["V"] = ov
                    _set_zn_from_val(self.flags, v)
                    self._on_execute(f"SHL {dst}")
                    ch = {dst: v}
                else:
                    # SHR
                    shr8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
                    res_u8 = self._read_u8_from_group("RES")
                    v = res_u8 if res_u8 < 128 else res_u8 - 256
                    self.mem.set(dst, v)
                    self.flags["C"] = 1 if (_to_u8(a) & 0x01) else 0
                    self.flags["V"] = 0
                    _set_zn_from_val(self.flags, v)
                    self._on_execute(f"SHR {dst}")
                    ch = {dst: v}
            elif op4 == OPCODES["NEG"]:
                # Perform 0 - a via LUT
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                # Flags like SUB with a=0, b=a
                inputs_diff_sign = _sign_bit(0) != _sign_bit(a)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(0) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(0) >= _to_u8(a) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"NEG {dst}")
                ch = {dst: v}
        elif op4 == OPCODES["JMP"] or op4 == OPCODES["BR"]:
            # Relative jump/branch; arg8 is signed offset
            rel = int(arg8 if arg8 < 128 else arg8 - 256)
            if op4 == OPCODES["JMP"]:
                taken = True
                next_pc = cur_pc + 1 + rel
                self._on_execute(f"JMP rel {rel:+d} -> {next_pc:02d}")
            else:
                # Evaluate condition from dst4 nibble
                cond_n = int(dst4) & 0xF
                name_by_cond = {v: k for k, v in BR_COND.items()}
                cname = name_by_cond.get(cond_n, "BEQ")
                Z = self.flags.get("Z", 0)
                N = self.flags.get("N", 0)
                V = self.flags.get("V", 0)
                taken = (
                    (cname == "BEQ" and Z == 1) or
                    (cname == "BNE" and Z == 0) or
                    (cname == "BMI" and N == 1) or
                    (cname == "BPL" and N == 0) or
                    (cname == "BVS" and V == 1) or
                    (cname == "BVC" and V == 0) or
                    (cname == "BCS" and V == 1) or
                    (cname == "BCC" and V == 0)
                )
                if taken:
                    next_pc = cur_pc + 1 + rel
                    self._on_execute(f"{cname} taken rel {rel:+d} -> {next_pc:02d}")
                else:
                    self._on_execute(f"{cname} not-taken")
        else:
            self._on_execute(f"(unknown ISA op) {op4:X}")

        # WRITEBACK stage
        try:
            post_stage("WRITEBACK")
        except Exception:
            pass
        if ch:
            self._println(f"[WB]     {', '.join(f'{k}={v:4d}' for k,v in ch.items())}")
        else:
            self._println("[WB]     (no changes)")
        # If ALU overlay selected (DATA1), surface SRC1/SRC2/RES and flags here as well (ISA path)
        try:
            if getattr(self, "_space_mode", "DATA0") == "DATA1":
                s1 = self._read_u8_from_group("SRC1")
                s2 = self._read_u8_from_group("SRC2")
                r  = self._read_u8_from_group("RES")
                def _bits(u: int) -> str:
                    b = f"{u & 0xFF:08b}"
                    return b[:4] + " " + b[4:]
                z = self.flags.get("Z", 0); n = self.flags.get("N", 0); vf = self.flags.get("V", 0); c = self.flags.get("C", 0)
                rs = r if r < 128 else r - 256
                self._println(
                    f"[ALU]    SRC1=0x{s1:02X} ({_bits(s1)})  "
                    f"SRC2=0x{s2:02X} ({_bits(s2)})  "
                    f"RES=0x{r:02X} ({_bits(r)}) => {rs:4d} | Z={z} N={n} V={vf} C={c}"
                )
        except Exception:
            pass
        self._sync_flag_leds()
        self._maybe_pause()

        # If a reset occurred during pause handling, preserve PC set by reset
        if getattr(self, "_reset_pending", False):
            try:
                self._on_pc_advance(start_pc, self.pc.value)
            except Exception:
                pass
            self._reset_pending = False
            if self.halted:
                self._on_halt()
            return not self.halted

        # Advance PC normally
        old_pc = start_pc
        self.pc.value = next_pc
        self._on_pc_advance(old_pc, self.pc.value)
        # Break on control-flow events when configured (BRANCH mode) in ISA path
        try:
            if self._break_mode == "BRANCH" and taken and self._space_mode in ("PROG", "DATA0", "DATA1"):
                # Pause instead of halt when branch/jump is taken
                self._println("[BRK]    BRANCH/JMP taken -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
        except Exception:
            pass
        if self.halted:
            self._on_halt()
        return not self.halted

    def _maybe_pause(self) -> None:
        """interactive 紐⑤뱶硫? ???곗궛 ?앸궇 ???ъ슜???낅젰 ?湲?
        [Enter]=???ㅽ뀦, 'c'=?곗냽 ?ㅽ뻾, 'q'=利됱떆 醫낅즺"""
        # LED control-plane active? skip interactive blocking
        if getattr(self, "cp_enabled", False):
            return
        if not self.interactive:
            return
        if self._continue_run:
            # 鍮꾩감?? 諛깃렇?쇱슫??紐낅졊 ??泥섎━ ??利됱떆 蹂듦?
            try:
                self._drain_cmd_queue()
            except Exception:
                pass
            return
        # Entering pause state: turn off stage indicators and show PAUSE
        try:
            clear_stages()
        except Exception:
            pass
        try:
            run_off()
        except Exception:
            pass
        # Prompt via stdout and read from the background command queue to avoid
        # nested input() calls fighting for stdin. This makes the prompt appear
        # immediately without needing an extra Enter press.
        prompt = (
            "[step] Enter=step | c/run/r/continue=continue | p/pause=pause | h/halt=halt | ehalt | "
            "reset | reset hard | reset bus | "
            "s/step/instr (ISA) | mi/micro (micro-lines) | cont (mode only) | trace on/off/mark | overlay alu/irpc/bus/service/none | q=quit > "
        )
        try:
            print(prompt, end="", flush=True)
        except Exception:
            pass
        # Ensure background reader is running
        try:
            if self._cmd_thread is None or not self._cmd_thread.is_alive():
                self._start_cmd_reader()
        except Exception:
            pass
        s = ""
        try:
            while True:
                try:
                    s = self._cmd_q.get(timeout=0.05)  # type: ignore[attr-defined]
                    s = (s or "").strip().lower()
                    break
                except Empty:
                    if self.halted:
                        s = ""
                        break
                    # keep waiting
                    pass
        except Exception:
            s = ""
        if s in ("c", "run", "r", "continue"):
            self._continue_run = True
            # Resume continuous run: show RUN (on)
            try:
                run_on()
            except Exception:
                pass
            try:
                set_run_state("RUN")
            except Exception:
                pass
        elif s == "q":
            self.halted = True
            # Remain paused on quit
            try:
                run_off()
            except Exception:
                pass
            try:
                set_run_state("HALT")
            except Exception:
                pass
        elif s == "pause" or s == "p":
            self._continue_run = False
            try:
                run_off()
            except Exception:
                pass
            try:
                set_run_state("PAUSE")
            except Exception:
                pass
        elif s == "halt" or s == "h":
            self.halted = True
            try:
                run_off()
            except Exception:
                pass
            try:
                set_run_state("HALT")
            except Exception:
                pass
        elif s == "ehalt":
            self.halted = True
            try:
                set_esc_state("EHALT")
            except Exception:
                pass
        elif s == "reset":
            try:
                set_esc_state("RESET")
            except Exception:
                pass
            try:
                self._soft_reset_visuals()
            except Exception:
                pass
            self._reset_pending = True
        elif s == "reset hard":
            try:
                set_esc_state("RESET")
            except Exception:
                pass
            try:
                self._hard_reset(recalibrate=False)
            except Exception:
                pass
            self._reset_pending = True
        elif s == "reset bus":
            try:
                self._reset_bus()
            except Exception:
                pass
        elif s == "instr" or s == "step" or s == "s":
            try:
                set_step_mode("INSTR")
            except Exception:
                pass
            try:
                # Switch to ISA instruction stepping (ensure stream/PC valid)
                self._enter_instr_mode()
            except Exception:
                pass
        elif s == "micro" or s == "mi":
            try:
                set_step_mode("MICRO")
            except Exception:
                pass
            try:
                # Switch to legacy micro-line stepping (populate program memory if needed)
                self._enter_micro_mode()
            except Exception:
                pass
        elif s == "cont":
            try:
                set_step_mode("CONT")
            except Exception:
                pass
            # Mode only; do not auto-continue here
        elif s.startswith("trace"):
            try:
                _, arg = (s + " ").split(" ", 1)
                arg = arg.strip()
            except Exception:
                arg = ""
            try:
                if arg.startswith("on"):
                    set_trace_state("ON")
                elif arg.startswith("off"):
                    set_trace_state("OFF")
                elif arg.startswith("mark"):
                    set_trace_state("MARK")
            except Exception:
                pass
        elif s.startswith("overlay"):
            try:
                _, arg = (s + " ").split(" ", 1)
                arg = arg.strip()
            except Exception:
                arg = ""
            try:
                if arg == "alu":
                    set_overlay_mode("ALU")
                elif arg == "irpc":
                    set_overlay_mode("IRPC")
                elif arg == "bus":
                    set_overlay_mode("BUS")
                elif arg == "service":
                    set_overlay_mode("SERVICE")
                else:
                    set_overlay_mode("NONE")
            except Exception:
                pass
        else:
            # Single-step resume: turn RUN on; next pause will turn it off again
            try:
                run_on()
            except Exception:
                pass
            try:
                set_run_state("RUN")
            except Exception:
                pass

    def _sync_flag_leds(self) -> None:
        """?꾩옱 Z/N/V 媛믪쓣 吏?뺣맂 ??LED??諛섏쁺"""
        if hasattr(self.mem, "set_flag"):
            for k, led in FLAG_LABELS.items():
                self.mem.set_flag(led, bool(self.flags.get(k, 0)))

    def run_led(self) -> None:
        """LED 而⑦듃濡??뚮젅?몄뿉 ?섑빐 寃뚯씠?낅릺???ㅽ뻾 猷⑦봽.
        grave/esc/tab/caps/left_shift ??而щ윭瑜?二쇨린?곸쑝濡??먮룆?섏뿬
        RUN/PAUSE/HALT/RESET/STEP/?쒕퉬???숈옉???섑뻾?쒕떎.
        """
        self._println("\n[RUN-LED] Starting LED-gated execution...")
        # Default to normal step mode (CONT); start paused
        try:
            set_step_mode("CONT")
        except Exception:
            pass
        try:
            set_run_state("PAUSE")
        except Exception:
            pass
        try:
            run_off()
        except Exception:
            pass
        # Start background command reader so console can set LED states
        try:
            if self._cmd_thread is None or not self._cmd_thread.is_alive():
                self._start_cmd_reader()
        except Exception:
            pass
        # State trackers (edge/one-shot behaviors & debug logs)
        last_run: str | None = None
        last_esc: str | None = None
        last_step: str | None = None
        last_trace: str | None = None
        last_overlay: str | None = None
        # One-shot trace marker armed flag (instance-level to coordinate with watch events)
        self._trace_mark_armed = getattr(self, "_trace_mark_armed", False)
        while True:
            # Drain any console commands to update LED states immediately
            try:
                self._drain_cmd_queue()
            except Exception:
                pass
            st: ControlStates = cp_poll()
            # Debug: state transitions
            try:
                if st.run != last_run:
                    self._println(f"[CP] RUN_STATE {last_run or '-'} -> {st.run}")
                    last_run = st.run
                if st.step != last_step:
                    self._println(f"[CP] STEP_MODE {last_step or '-'} -> {st.step}")
                    last_step = st.step
                if st.trace != last_trace:
                    self._println(f"[CP] TRACE {last_trace or '-'} -> {st.trace}")
                    if st.trace == "MARK" and last_trace != "MARK":
                        self._trace_mark_armed = True
                        self._println("[TRACE] MARK armed (one-shot)")
                    last_trace = st.trace
                if st.overlay != last_overlay:
                    self._println(f"[CP] OVERLAY {last_overlay or '-'} -> {st.overlay}")
                    last_overlay = st.overlay
            except Exception:
                pass
            # ESC edge-trigger handling (momentary)
            if st.esc == "EHALT" and last_esc != "EHALT":
                self._println("[CP] E-HALT edge -> HALT")
                self.halted = True
                # Single-step returns to PAUSE; continuous-run keeps RUN
                if not getattr(self, "_cp_continuous_run", False):
                    try:
                        run_off()
                    except Exception:
                        pass
                break
            if st.esc == "RESET" and last_esc != "RESET":
                self._println("[CP] RESET edge -> soft reset visuals")
                self._soft_reset_visuals()
                if not getattr(self, "_cp_continuous_run", False):
                    try:
                        run_off()
                    except Exception:
                        pass
                self._reset_pending = True
                time.sleep(0.02)
                last_esc = st.esc
                continue
            last_esc = st.esc

            # Update Break/Watch/Space config from LEDs
            try:
                # tab: break mode (CONT=None, INSTR=BRANCH, MICRO=WWRITE)
                self._break_mode = ("NONE" if st.step == "CONT" else ("BRANCH" if st.step == "INSTR" else "WWRITE"))
                # caps: watch mode (OFF=None, ON=READ, MARK=WRITE)
                self._watch_mode = ("NONE" if st.trace == "OFF" else ("READ" if st.trace == "ON" else "WRITE"))
                # left_shift: space/bank (NONE=DATA0, ALU=DATA1, IRPC=PROG, BUS=IO)
                space_map = {"NONE": "DATA0", "ALU": "DATA1", "IRPC": "PROG", "BUS": "IO", "SERVICE": "SERVICE"}
                self._space_mode = space_map.get(st.overlay, "DATA0")
            except Exception:
                pass

            # 二??곹깭(RUN/PAUSE/HALT/FAULT)
            if st.run in ("HALT", "FAULT"):
                self.halted = True
                try:
                    run_off()
                except Exception:
                    pass
                break
            if st.run == "PAUSE":
                try:
                    if not getattr(self, "_cp_continuous_run", False):
                        run_off()
                except Exception:
                    pass
                # SERVICE overlay acts only during pause
                try:
                    if st.overlay == "SERVICE":
                        self._println("[SERVICE] request -> calibrate IR (if cooldown passed)")
                    ran = cp_service(st)
                    if ran:
                        self._println("[SERVICE] calibrate IR completed")
                except Exception:
                    pass
                time.sleep(0.02)
                continue

            # RUN ?곹깭: ?ㅽ뀦 紐⑤뱶???곕씪 ?섑뻾
            cont = True
            if st.step == "INSTR":
                # Reset per-step write flag before executing a step
                self._write_hit_in_step = False
                try:
                    cont = self.step()
                except Exception as ex:
                    try:
                        self._trap_fault("LED INSTR step", ex)
                    except Exception:
                        pass
                    break
                # Trace gate
                try:
                    if st.trace == "ON" or self._trace_mark_armed:
                        marker_now = bool(self._trace_mark_armed and self._write_hit_in_step)
                        self._trace_log.append({
                            "pc": int(self.pc.value),
                            "flags": dict(self.flags),
                            "marker": marker_now,
                        })
                        self._println(f"[TRACE] appended pc={int(self.pc.value)} marker={marker_now}")
                        if marker_now:
                            # Consume one-shot mark and revert caps to ON
                            self._trace_mark_armed = False
                            try:
                                set_trace_state("ON")
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    if not getattr(self, "_cp_continuous_run", False):
                        run_off()
                except Exception:
                    pass
                try:
                    cp_service(st)
                except Exception:
                    pass
                if not cont:
                    break
                time.sleep(0.01)
                continue
            elif st.step == "MICRO":
                # Micro mode; execute one ISA step (or micro) and honor continuous-run
                self._write_hit_in_step = False
                try:
                    cont = self.step()
                except Exception as ex:
                    try:
                        self._trap_fault("LED MICRO step", ex)
                    except Exception:
                        pass
                    break
                try:
                    if st.trace == "ON" or self._trace_mark_armed:
                        marker_now = bool(self._trace_mark_armed and self._write_hit_in_step)
                        self._trace_log.append({
                            "pc": int(self.pc.value),
                            "flags": dict(self.flags),
                            "marker": marker_now,
                        })
                        self._println(f"[TRACE] appended pc={int(self.pc.value)} marker={marker_now}")
                        if marker_now:
                            self._trace_mark_armed = False
                            try:
                                set_trace_state("ON")
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    # Only auto-pause after a step when NOT in continuous-run.
                    if not getattr(self, "_cp_continuous_run", False):
                        run_off()
                except Exception:
                    pass
                try:
                    cp_service(st)
                except Exception:
                    pass
                if not cont:
                    break
                time.sleep(0.01)
                continue
            else:  # CONT
                self._write_hit_in_step = False
                try:
                    cont = self.step()
                except Exception as ex:
                    try:
                        self._trap_fault("LED CONT step", ex)
                    except Exception:
                        pass
                    break
                try:
                    if st.trace == "ON" or self._trace_mark_armed:
                        marker_now = bool(self._trace_mark_armed and self._write_hit_in_step)
                        self._trace_log.append({
                            "pc": int(self.pc.value),
                            "flags": dict(self.flags),
                            "marker": marker_now,
                        })
                        self._println(f"[TRACE] appended pc={int(self.pc.value)} marker={marker_now}")
                        if marker_now:
                            self._trace_mark_armed = False
                            try:
                                set_trace_state("ON")
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    cp_service(st)
                except Exception:
                    pass
                if not cont:
                    break

        # 醫낅즺 泥섎━
        try:
            clear_stages()
        except Exception:
            pass
        self._println("[RUN] Execution finished.\n")
        try:
            run_off()
        except Exception:
            pass

    def _soft_reset_visuals(self) -> None:
        """?꾨줈洹몃옩? ?좎???梨?PC/IR/Flags 諛??쒖떆瑜?珥덇린??"""
        self.pc.reset()
        self.halted = False
        self.ir.clear()
        self.flags["Z"] = 0
        self.flags["N"] = 0
        self.flags["V"] = 0
        self.flags["C"] = 0
        try:
            self._sync_flag_leds()
        except Exception:
            pass
        try:
            clear_stages()
        except Exception:
            pass
        try:
            clear_ir()
        except Exception:
            pass
        try:
            clear_pc()
        except Exception:
            pass
        # Ensure bus lines are idle
        try:
            self._reset_bus()
        except Exception:
            pass

    def _hard_reset(self, *, recalibrate: bool = False) -> None:
        """Cold-like reset: soft visuals + zeroize variables and reset UI panel.
        - Soft reset visuals (PC/IR/flags/stages/PC indicator)
        - Zero all VARIABLE_KEYS in memory
        - Clear trace log and set panel switches to defaults (CONT/OFF/NONE)
        - Optionally request IR calibration
        """
        # Base soft reset of core visual/state
        self._soft_reset_visuals()

        # Zeroize variables (memory) and visually turn them OFF per project convention
        try:
            for name in list(VARIABLE_KEYS):
                try:
                    # Logical content reset (if any agent reads values later)
                    self.mem.set(name, 0)
                except Exception:
                    pass
                try:
                    # Visual OFF (black) — variables appear cleared on keyboard
                    set_key_color(name, cp.BLACK)
                except Exception:
                    pass
        except Exception:
            pass

        # Clear trace log buffer
        try:
            self._trace_log.clear()
        except Exception:
            self._trace_log = []

        # Reset control panel indicators/modes to a clean default
        try:
            set_step_mode("CONT")
        except Exception:
            pass
        try:
            set_trace_state("OFF")
        except Exception:
            pass
        try:
            set_overlay_mode("NONE")
        except Exception:
            pass
        try:
            set_run_state("PAUSE")
        except Exception:
            pass

        # Optionally recalibrate IR decoding colors
        if recalibrate:
            try:
                calibrate_ir(samples=2, settle_ms=8, debug=False)
            except Exception:
                pass

    def _reset_bus(self) -> None:
        """Reset/clear LED-bus control lines without touching CPU/vars.
        - Abort any ongoing cycle and turn ADDR_VALID/RD/WR off
        - Ensure ACK is off
        - Preserve PC/IR/flags/memory
        """
        # If BusMemory wrapper present, use its BusInterface
        try:
            bus = getattr(self.mem, "_bus", None)
        except Exception:
            bus = None
        if bus is not None:
            try:
                bus.end_cycle()  # ADDR_VALID/RD/WR -> OFF
            except Exception:
                pass
            try:
                # Best-effort force ACK off (private helper)
                if hasattr(bus, "_ack_off"):
                    bus._ack_off()
            except Exception:
                pass
            return

        # Fallback: directly drive keys to OFF using presets
        try:
            from openrgb.utils import RGBColor
            from rgb_controller import set_key_color
            _, off_addr = BINARY_COLORS.get(BUS_ADDR_VALID, ((0,0,0),(0,0,0)))
            _, off_rd   = BINARY_COLORS.get(BUS_RD,         ((0,0,0),(0,0,0)))
            _, off_wr   = BINARY_COLORS.get(BUS_WR,         ((0,0,0),(0,0,0)))
            _, off_ack  = BINARY_COLORS.get(BUS_ACK,        ((0,0,0),(0,0,0)))
            set_key_color(BUS_ADDR_VALID, RGBColor(*off_addr))
            set_key_color(BUS_RD,         RGBColor(*off_rd))
            set_key_color(BUS_WR,         RGBColor(*off_wr))
            set_key_color(BUS_ACK,        RGBColor(*off_ack))
        except Exception:
            pass

    def run(self) -> None:
        self._println("\n[RUN] Starting execution...")
        # Show RUN when entering the run loop
        try:
            run_on()
        except Exception:
            pass
        # Start background command reader in interactive mode
        try:
            if self.interactive and not self.cp_enabled:
                self._start_cmd_reader()
        except Exception:
            pass
        while True:
            try:
                cont = self.step()
            except Exception as ex:
                # Hardware-centric trap: latch HALT, report reason, keep process alive
                try:
                    self._trap_fault("RUN step", ex)
                except Exception:
                    pass
                break
            if not cont:
                break
        # ?ㅽ뻾 醫낅즺 利됱떆 ?④퀎 ?쒖떆 ?뚮벑(WRITEBACK ?ы븿)
        try:
            clear_stages()
        except Exception:
            pass
        self._println("[RUN] Execution finished.\n")
        # Ensure indicator shows PAUSE at the end
        try:
            run_off()
        except Exception:
            pass

    def _group_labels(self, grp: str):
        g = grp.upper()
        if g == "SRC1": return SRC1
        if g == "SRC2": return SRC2
        if g == "RES":  return RES
        raise ValueError(f"unknown bit-group: {grp}")

    def _write_u8_to_group(self, grp: str, u8: int):
        labels = self._group_labels(grp)
        u8 &= 0xFF
        width = len(labels)
        # labels[-1]??LSB媛 ?섎룄濡???씤?깆떛
        for i in range(width):  # i=0..7 -> 鍮꾪듃 i
            bit = (u8 >> i) & 1
            lab = labels[width - 1 - i]
            self.mem.set(lab, bit)

    def _clear_group(self, grp: str):
        for lab in self._group_labels(grp):
            self.mem.set(lab, 0)

    def _read_u8_from_group(self, grp: str) -> int:
        labels = self._group_labels(grp)
        width = len(labels)
        val = 0
        # labels[-1]??LSB ????씤?깆떛?쇰줈 ?쎌뼱??i踰덉㎏ 鍮꾪듃濡?
        for i in range(width):  # i=0..7
            lab = labels[width - 1 - i]
            val |= (int(self.mem.get(lab)) & 1) << i
        return val & 0xFF

    # ---------- ?대? ?ㅽ뻾湲?----------
        # ---------- interactive helpers ----------
    def _start_cmd_reader(self) -> None:
        if self._cmd_thread is not None and self._cmd_thread.is_alive():
            return
        def _reader():
            while not self.halted:
                try:
                    # No prompt here; the main thread prints the appropriate
                    # step/command prompt and we just read lines.
                    s = input().strip().lower()
                except EOFError:
                    break
                except Exception:
                    continue
                try:
                    self._cmd_q.put(s)
                except Exception:
                    pass
        try:
            th = threading.Thread(target=_reader, daemon=True)
            th.start()
            self._cmd_thread = th
        except Exception:
            self._cmd_thread = None

    def _drain_cmd_queue(self) -> None:
        while True:
            try:
                s = self._cmd_q.get_nowait()
            except Empty:
                break
            try:
                self._println(f"[CMD] {s}")
                self._process_command_line(s)
            except Exception:
                pass

    def _process_command_line(self, s: str) -> None:
        s = (s or "").strip().lower()
        if s == "":
            # Single-step request in LED mode
            self._cp_single_step = True
            self._cp_continuous_run = False
            try:
                run_on(); set_run_state("RUN")
            except Exception:
                pass
            return
        if s in ("c", "run", "r", "continue"):
            # Continuous run request
            self._continue_run = True
            self._cp_continuous_run = True
            self._cp_single_step = False
            try:
                run_on(); set_run_state("RUN")
            except Exception:
                pass
            return
        if s in ("q",):
            self.halted = True
            try:
                run_off(); set_run_state("HALT")
            except Exception:
                pass
            return
        if s in ("pause", "p"):
            self._continue_run = False
            self._cp_continuous_run = False
            try:
                run_off(); set_run_state("PAUSE")
            except Exception:
                pass
            return
        if s in ("halt", "h"):
            self.halted = True
            self._cp_continuous_run = False
            try:
                run_off(); set_run_state("HALT")
            except Exception:
                pass
            return
        if s == "ehalt":
            self.halted = True
            try:
                set_esc_state("EHALT")
            except Exception:
                pass
            return
        if s == "reset":
            try:
                set_esc_state("RESET")
            except Exception:
                pass
            try:
                self._soft_reset_visuals()
            except Exception:
                pass
            self._reset_pending = True
            return
        if s == "reset hard":
            try:
                set_esc_state("RESET")
            except Exception:
                pass
            try:
                self._hard_reset(recalibrate=False)
            except Exception:
                pass
            self._reset_pending = True
            return
        if s == "reset bus":
            try:
                self._reset_bus()
            except Exception:
                pass
            return
        if s == "reset hard":
            try:
                set_esc_state("RESET")
            except Exception:
                pass
            try:
                self._hard_reset(recalibrate=False)
            except Exception:
                pass
            return
        if s == "reset bus":
            try:
                self._reset_bus()
            except Exception:
                pass
            return
        if s in ("instr", "step", "s"):
            try:
                set_step_mode("INSTR")
            except Exception:
                pass
            try:
                self._enter_instr_mode()
            except Exception:
                pass
            return
        # Support two-word forms like 'step instr', 'step micro', 'step cont'
        if s.startswith("step ") or s.startswith("s "):
            try:
                _, arg = (s + " ").split(" ", 1)
                arg = (arg or "").strip()
            except Exception:
                arg = ""
            try:
                if arg.startswith("instr"):
                    set_step_mode("INSTR"); self._enter_instr_mode()
                elif arg.startswith("micro") or arg.startswith("mi"):
                    set_step_mode("MICRO"); self._enter_micro_mode()
                elif arg.startswith("cont"):
                    set_step_mode("CONT")
                else:
                    # default to INSTR if unspecified/unknown
                    set_step_mode("INSTR"); self._enter_instr_mode()
            except Exception:
                pass
            return
        if s in ("micro", "mi"):
            try:
                # Only switch step mode; don't force RUN here. Also toggle to micro interpreter.
                set_step_mode("MICRO"); self._enter_micro_mode()
            except Exception:
                pass
            return
        if s == "cont":
            try:
                # Mode only; don't auto-continue
                set_step_mode("CONT")
            except Exception:
                pass
            return
        if s.startswith("trace"):
            try:
                _, arg = (s + " ").split(" ", 1)
                arg = arg.strip()
            except Exception:
                arg = ""
            try:
                if arg.startswith("on"):
                    set_trace_state("ON")
                elif arg.startswith("off"):
                    set_trace_state("OFF")
                elif arg.startswith("mark"):
                    set_trace_state("MARK")
            except Exception:
                pass
            return
        if s.startswith("overlay"):
            try:
                _, arg = (s + " ").split(" ", 1)
                arg = arg.strip()
            except Exception:
                arg = ""
            try:
                if arg == "alu":
                    set_overlay_mode("ALU")
                elif arg == "irpc":
                    set_overlay_mode("IRPC")
                elif arg == "bus":
                    set_overlay_mode("BUS")
                elif arg == "service":
                    set_overlay_mode("SERVICE")
                else:
                    set_overlay_mode("NONE")
            except Exception:
                pass
            return
        try:
            run_on(); set_run_state("RUN")
        except Exception:
            pass

    def _exec_one(self, op: str, args: tuple[Any, ...]) -> Dict[str, int]:
        ch: Dict[str, int] = {}

        # --- NOP/LABEL/HALT/PRINT ---
        if op == "NOP":
            self._on_execute("NOP")
            return ch

        if op == "LABEL":
            name = str(args[0])
            self._on_execute(f"LABEL {name}")
            return ch

        if op == "HALT":
            self._on_execute("HALT")
            self.halted = True
            return ch

        if op == "PRINT":
            var = str(args[0])
            val = self.mem.get(var)
            self._on_execute(f"PRINT {var} -> {val}")
            return ch
        
        if op == "PRINT_RES":
            u8 = self._read_u8_from_group("RES")
            v  = u8 if u8 < 128 else u8 - 256   # two's complement
            self._on_execute(f"PRINT_RES -> {v}")
            return ch

        # --- MOV/MOVI ---
        if op == "MOVI":
            dst, imm = args
            self.mem.set(str(dst), int(imm))
            self._on_execute(f"MOVI {dst}, #{imm}")
            ch[str(dst)] = self.mem.get(str(dst))
            return ch

        if op == "MOV":
            dst, src = args
            v = self.mem.get(str(src))
            self.mem.set(str(dst), v)
            self._on_execute(f"MOV  {dst}, {src} ; {dst}={v}")
            ch[str(dst)] = self.mem.get(str(dst))
            return ch
        
        if op == "UNPACK1":
            (var,) = args
            v = self.mem.get(str(var))         # -128..127
            self._write_u8_to_group("SRC1", v & 0xFF)
            self._on_execute(f"UNPACK1 {var} -> SRC1")
            return ch

        if op == "UNPACK2":
            (var,) = args
            v = self.mem.get(str(var))
            self._write_u8_to_group("SRC2", v & 0xFF)
            self._on_execute(f"UNPACK2 {var} -> SRC2")
            return ch

        if op == "UNPACK":
            var, grp = args
            v = self.mem.get(str(var))
            self._write_u8_to_group(str(grp), v & 0xFF)
            self._on_execute(f"UNPACK {var} -> {grp}")
            return ch

        # LOADI8_BITS
        if op == "LOADI8_BITS":
            grp, imm = args
            self._write_u8_to_group(str(grp), int(imm))
            self._on_execute(f"LOADI8_BITS {grp}, #{int(imm)&0xFF}")
            return ch

        # CLEARBITS
        if op == "CLEARBITS":
            (grp,) = args
            self._clear_group(str(grp))
            self._on_execute(f"CLEARBITS {grp}")
            return ch

        # COPYBITS
        if op == "COPYBITS":
            dst, src = args
            src_labels = self._group_labels(str(src))
            dst_labels = self._group_labels(str(dst))
            
            # 1. Read all bits from source group first
            bits = []
            for label in src_labels:
                bits.append(int(self.mem.get(label)) & 1)

            # 2. Then write all bits to destination group
            for i, label in enumerate(dst_labels):
                self.mem.set(label, bits[i])
            
            self._on_execute(f"COPYBITS {dst}, {src}")
            return ch

        # --- ADD/ADDI (signed: Z/N/V 媛깆떊) ---
        if op == "ADDI":
            dst, imm = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            b = int(imm)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_same_sign = _sign_bit(a) == _sign_bit(b)
            self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry: unsigned carry out
            self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(
                f"ADDI {dst}, #{imm} ; via LUT {dst_name}:{a}+{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}"
            )
            ch[dst_name] = v
            return ch

        if op == "ADD":
            dst, src = args
            dst_name = str(dst)
            src_name = str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_same_sign = _sign_bit(a) == _sign_bit(b)
            self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry: unsigned carry out
            self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(
                f"ADD  {dst}, {src} ; via LUT {dst_name}:{a}+{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}"
            )
            ch[dst_name] = v
            return ch

        if op == "ADD8":
            # Perform addition via LUT and update flags like ADD
            a_u8 = self._read_u8_from_group("SRC1")
            b_u8 = self._read_u8_from_group("SRC2")
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            # Signed overflow: inputs same sign and result sign differs from a
            inputs_same_sign = (1 if (a_u8 & 0x80) else 0) == (1 if (b_u8 & 0x80) else 0)
            self.flags["V"] = 1 if inputs_same_sign and ((1 if (a_u8 & 0x80) else 0) != (1 if (res_u8 & 0x80) else 0)) else 0
            # Unsigned carry out
            self.flags["C"] = 1 if (a_u8 + b_u8) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute("ADD8 (via LUT) ; RES -> SRC1 + SRC2")
            return ch

        # --- SUB/SUBI (signed: Z/N/V 媛깆떊) ---
        if op == "SUBI":
            dst, imm = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            b = int(imm)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' for subtraction
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUBI {dst}, #{imm} ; via LUT {dst_name}:{a}-{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[dst_name] = v
            return ch

        if op == "SUB":
            dst, src = args
            dst_name = str(dst)
            src_name = str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' for subtraction
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUB  {dst}, {src} ; via LUT {dst_name}:{a}-{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[dst_name] = v
            return ch

        if op == "SUB8":
            # Perform subtraction via LUT and update flags like SUB
            a_u8 = self._read_u8_from_group("SRC1")
            b_u8 = self._read_u8_from_group("SRC2")
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            # Signed overflow on subtraction: inputs different sign and result sign differs from a
            inputs_diff_sign = ((a_u8 ^ b_u8) & 0x80) != 0
            self.flags["V"] = 1 if inputs_diff_sign and (((a_u8 ^ res_u8) & 0x80) != 0) else 0
            # Carry as 'no borrow'
            self.flags["C"] = 1 if a_u8 >= b_u8 else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute("SUB8 (via LUT) ; RES -> SRC1 - SRC2")
            return ch

        if op == "PACK":
            (var,) = args
            u8 = self._read_u8_from_group("RES")
            v = u8 if u8 < 128 else u8 - 256
            self.mem.set(str(var), v)
            ch[str(var)] = v
            self._on_execute(f"PACK {var} <- RES ({v})")
            return ch

        # --- 鍮꾪듃 ?곗궛 (Z/N 媛깆떊, V=0) ---
        if op in ("AND", "OR", "XOR"):
            dst, src = args
            dst_name, src_name = str(dst), str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))

            lut_func = {
                "AND": and8_via_lut, "OR": or8_via_lut, "XOR": xor8_via_lut
            }[op]
            lut_func(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            op_symbol = {'AND':'&', 'OR':'|', 'XOR':'^'}[op]
            self._on_execute(f"{op:<4} {dst}, {src} ; via LUT {dst_name}:{a}{op_symbol}{b}->{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        # --- ?쒗봽??---
        if op == "SHL":
            dst, = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            
            self._write_u8_to_group("SRC1", _to_u8(a))
            shl8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
            
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            
            # Carry out from MSB before shift
            self.flags["C"] = 1 if (_to_u8(a) & 0x80) else 0
            # SHL overflow: 理쒖긽??鍮꾪듃 蹂???щ?濡??먮떒
            ov = 1 if (_sign_bit(a) != _sign_bit(v)) else 0
            self.mem.set(dst_name, v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHL  {dst} ; via LUT {a:4d}<<1 -> {v:4d} | V={ov} Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        if op == "SHR":
            dst, = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            shr8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            # Carry out from LSB
            self.flags["C"] = 1 if (_to_u8(a) & 0x01) else 0
            self.flags["V"] = 0 # ASR? ?ㅻ쾭?뚮줈???놁쓬
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHR  {dst} ; via LUT {a:4d}>>1 -> {v:4d} | V=0 Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        # --- 鍮꾧탳/遺꾧린 ---
        if op == "CMP" or op == "CMPI":
            a_name, b_arg = args
            a = self.mem.get(str(a_name))
            b = int(b_arg) if op == "CMPI" else self.mem.get(str(b_arg))

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' like SUB
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            
            b_str = f"#{b}" if op == "CMPI" else str(b_arg)
            self._on_execute(f"{op:<4} {a_name}, {b_str} ; via LUT ({a}-{b})  | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            return ch

        if op == "JMP":
            label = str(args[0])
            addr = self._resolve_label(label)
            if addr is None:
                self._on_execute(f"JMP {label} ; <LABEL NOT FOUND> -> HALT")
                self.halted = True
                return ch
            self.pc.value = addr
            self._pc_overridden = True
            self._on_execute(f"JMP  {label} ; PC={addr:02d}")
            return ch

        if op == "BEQ":
            label = str(args[0])
            if self.flags.get("Z", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BEQ {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BEQ  {label} ; Z=1 ??PC={addr:02d}")
            else:
                self._on_execute(f"BEQ  {label} ; Z=0  | no-branch")
            return ch

        if op == "BNE":
            label = str(args[0])
            if self.flags.get("Z", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BNE {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BNE  {label} ; Z=0 ??PC={addr:02d}")
            else:
                self._on_execute(f"BNE  {label} ; Z=1  | no-branch")
            return ch

        if op == "BMI":
            label = str(args[0])
            if self.flags.get("N", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BMI {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BMI  {label} ; N=1 ??PC={addr:02d}")
            else:
                self._on_execute(f"BMI  {label} ; N=0  | no-branch")
            return ch

        if op == "BPL":
            label = str(args[0])
            if self.flags.get("N", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BPL {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BPL  {label} ; N=0 ??PC={addr:02d}")
            else:
                self._on_execute(f"BPL  {label} ; N=1  | no-branch")
            return ch

        # NEW: BVS/BVC
        if op == "BVS":
            label = str(args[0])
            if self.flags.get("V", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BVS {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BVS  {label} ; V=1 ??PC={addr:02d}")
            else:
                self._on_execute(f"BVS  {label} ; V=0  | no-branch")
            return ch

        if op == "BVC":
            label = str(args[0])
            if self.flags.get("V", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BVC {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BVC  {label} ; V=0 ??PC={addr:02d}")
            else:
                self._on_execute(f"BVC  {label} ; V=1  | no-branch")
            return ch

        # ?섏쐞 ?명솚: BCS/BCC ??V ?ъ슜
        if op == "BCS":
            label = str(args[0])
            if self.flags.get("V", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCS {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCS  {label} ; (alias V=1) ??PC={addr:02d}")
            else:
                self._on_execute(f"BCS  {label} ; V=0  | no-branch")
            return ch

        if op == "BCC":
            label = str(args[0])
            if self.flags.get("V", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCC {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCC  {label} ; (alias V=0) ??PC={addr:02d}")
            else:
                self._on_execute(f"BCC  {label} ; V=1  | no-branch")
            return ch

        # ?뺤쓽 ????op
        self._on_execute(f"(unknown op) {op} {args}")
        return ch

    def _resolve_label(self, name: str) -> int | None:
        addr = self.prog.get_label_addr(name)
        return addr

    # ---------- 肄섏넄 ??----------
    def _on_fetch(self, text: str) -> None:
        # Stage: FETCH (鍮꾨룞湲??쒖떆)
        try:
            post_stage("FETCH")
        except Exception:
            pass
        # Update PC indicator for current instruction address
        try:
            update_pc(self.pc.value)
        except Exception:
            pass
        # Try to render approximate machine encoding as 2-byte binary (xxxx xxxx xxxx xxxx)
        enc_bits = ""
        try:
            enc = encode_from_source_line_fixed(text)
            if enc is not None:
                op4, dst4, arg8 = enc
                b0 = ((op4 & 0xF) << 4) | (dst4 & 0xF)
                b1 = arg8 & 0xFF
                bits16 = f"{(b0<<8)|b1:016b}"
                grouped = " ".join(bits16[i:i+4] for i in range(0, 16, 4))
                enc_bits = f" | ENC {grouped}"
                # Also set IR visualization here (avoid re-parsing later)
                try:
                    set_ir(op4, dst4, arg8)
                except Exception:
                    pass
                try:
                    self._maybe_watch_prog_event("IR_WRITE")
                except Exception:
                    pass
        except Exception:
            enc_bits = ""
        self._println(f"[FETCH] PC={self.pc.value:02d}  line='{text}'{enc_bits}")
        # IR already updated above

    def _on_decode(self, decoded: Tuple[str, tuple[Any, ...]]) -> None:
        op, args = decoded
        # Stage: DECODE (鍮꾨룞湲??쒖떆)
        try:
            post_stage("DECODE")
        except Exception:
            pass
        self._println(f"[DECODE] {op} {args}")
        # IR??FETCH ?④퀎?먯꽌 怨좎닔以 ?쇱씤 湲곗??쇰줈 ?대? ?쒖떆??
    def _on_execute(self, desc: str) -> None:
        # Stage: EXECUTE (鍮꾨룞湲??쒖떆)
        try:
            post_stage("EXECUTE")
        except Exception:
            pass
        self._println(f"[EXEC]   {desc}")

    def _on_writeback(self, changes: Dict[str, int]) -> None:
        if changes:
            ch = ", ".join(f"{k}={v:4d}" for k, v in changes.items())
            # Stage: WRITEBACK (鍮꾨룞湲??쒖떆)
            try:
                post_stage("WRITEBACK")
            except Exception:
                pass
            self._println(f"[WB]     {ch}")
        else:
            # Stage: WRITEBACK (鍮꾨룞湲??쒖떆: 蹂寃??놁뼱???숈씪)
            try:
                post_stage("WRITEBACK")
            except Exception:
                pass
            self._println("[WB]     (no changes)")
        # If ALU overlay selected, also surface SRC1/SRC2/RES and flags to make overlay meaningful
        try:
            if getattr(self, "_space_mode", "DATA0") == "DATA1":
                s1 = self._read_u8_from_group("SRC1")
                s2 = self._read_u8_from_group("SRC2")
                r  = self._read_u8_from_group("RES")
                def _bits(u: int) -> str:
                    b = f"{u & 0xFF:08b}"
                    return b[:4] + " " + b[4:]
                z = self.flags.get("Z", 0); n = self.flags.get("N", 0); vflag = self.flags.get("V", 0); c = self.flags.get("C", 0)
                rs = r if r < 128 else r - 256
                self._println(
                    f"[ALU]    SRC1=0x{s1:02X} ({_bits(s1)})  "
                    f"SRC2=0x{s2:02X} ({_bits(s2)})  "
                    f"RES=0x{r:02X} ({_bits(r)}) => {rs:4d} | Z={z} N={n} V={vflag} C={c}"
                )
        except Exception:
            pass

    def _on_pc_advance(self, old: int, new: int) -> None:
        self._println(f"[PC]     {old:02d} -> {new:02d}")
        try:
            self._maybe_watch_prog_event("PC_WRITE")
        except Exception:
            pass

    def _on_halt(self) -> None:
        self._println("[HALT]   Program finished or PC out of range.")
        # Clear indicators on halt for a clean stop
        try:
            clear_stages()
        except Exception:
            pass
        # IR off on halt
        try:
            clear_ir()
        except Exception:
            pass
        # Turn off PC indicators on halt
        try:
            clear_pc()
        except Exception:
            pass
        # Ensure PAUSE on HALT
        try:
            run_off()
        except Exception:
            pass

    # ---- Fault trap: convert unexpected exceptions into a latched HALT ----
    def _trap_fault(self, where: str, ex: Exception) -> None:
        """Hardware-centric fault handling: do not crash the host process.
        - Latch HALT, print compact reason and current PC/op context
        - Best-effort update panel to HALT (red), but keep power on
        """
        self.halted = True
        # Summarize context
        try:
            pc_s = f"PC={int(self.pc.value):02d}"
        except Exception:
            pc_s = "PC=?"
        try:
            dec = getattr(self.ir, "decoded", None)
            opctx = f" op={str(dec[0])} args={dec[1]}" if dec else ""
        except Exception:
            opctx = ""
        msg = f"[FAULT] {where} -> HALT | {pc_s}{opctx} | {ex.__class__.__name__}: {ex}"
        try:
            self._println(msg)
        except Exception:
            pass
        # Indicate HALT on the panel (do not toggle power)
        try:
            from utils.control_plane import set_run_state
            run_off()
            set_run_state("HALT")
        except Exception:
            pass

    # ---- Watch/Break integration (bus events) ----
    def on_bus_mem_event(self, ev: Dict[str, Any]) -> None:
        """Called by BusMemory after each get/set on variables.
        ev = { 'dir': 'READ'|'WRITE', 'name': 'a'.., 'value': int }
        Applies watch/break rules based on caps_lock(tab)/left_shift states.
        """
        try:
            name = str(ev.get('name', ''))
            direction = str(ev.get('dir', ''))
        except Exception:
            return
        # Optional latency metadata from BusMemory
        lat_ms: int | None = None
        try:
            lat_ms = int(ev.get('lat_ms'))
        except Exception:
            lat_ms = None

        # DATA spaces: normal variable watch/break
        if self._space_mode in ("DATA0", "DATA1"):
            if name not in VARIABLE_KEYS:
                return
            if self._watch_mode == "READ" and direction == "READ":
                m = f"[WATCH] READ hit at var '{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            # Record that a WRITE happened in this step; used to consume one-shot MARK after the step.
            if direction == "WRITE":
                try:
                    self._write_hit_in_step = True
                except Exception:
                    pass
            if self._watch_mode == "WRITE" and direction == "WRITE":
                m = f"[WATCH] WRITE hit at var '{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            # Break mode 'WWRITE' halts on any variable write
            if self._break_mode == "WWRITE" and direction == "WRITE":
                m = f"[BRK]    WRITE break at var '{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
            return

        # IO space: bus-focused watch using same READ/WRITE semantics
        if self._space_mode == "IO":
            if self._watch_mode == "READ" and direction == "READ":
                m = "[BUS]    READ cycle"
                if name:
                    m += f" var='{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            if direction == "WRITE":
                try:
                    self._write_hit_in_step = True
                except Exception:
                    pass
            if self._watch_mode == "WRITE" and direction == "WRITE":
                m = "[BUS]    WRITE cycle"
                if name:
                    m += f" var='{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
                return
            if self._break_mode == "WWRITE" and direction == "WRITE":
                m = "[BUS-BRK] WRITE cycle"
                if name:
                    m += f" var='{name}'"
                if lat_ms is not None:
                    m += f" (lat {lat_ms}ms)"
                self._println(m + " -> PAUSE")
                try:
                    run_off(); set_run_state("PAUSE")
                except Exception:
                    pass
            return

    def _println(self, s: str) -> None:
        if self.debug:
            print(s)


