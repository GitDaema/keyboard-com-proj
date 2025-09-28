from typing import List, Tuple, Any

# Reuse your existing parser and encoder
from sim.parser import parse_line, preprocess_program
from utils.ir_indicator import (
    encode_from_decoded,
    encode_from_source_line_fixed,
    _MACHINE_OPS,  # 내부 정의: 기계어급 명령 집합
)


def _format_op(op: str, args: tuple[Any, ...]) -> str:
    op_u = str(op).upper()
    if not args:
        return op_u
    # Join with comma+space for two-arg forms, space for single-arg
    if len(args) == 1:
        return f"{op_u} {args[0]}"
    return f"{op_u} {args[0]}, {args[1]}"


def _encode_to_bytes(enc: Tuple[int, int, int]) -> Tuple[int, int, str]:
    op4, dst4, arg8 = enc
    b0 = ((int(op4) & 0xF) << 4) | (int(dst4) & 0xF)
    b1 = int(arg8) & 0xFF
    bits16 = f"{((b0 << 8) | b1):016b}"
    grouped = " ".join(bits16[i : i + 4] for i in range(0, 16, 4))
    return b0, b1, grouped


def print_listing(lines: List[str], *, preprocess: bool = True, debug: bool = False) -> None:
    """
    고급 명령어 줄(List[str])을 받아, 파서가 생성한 어셈블리 명령어와
    근사 기계어 2바이트(op4|dst4, arg8)를 한 줄씩 보기 좋게 출력.

    - preprocess=True 인 경우, IF/ELSE/END 블록을 분해한 확장 라인 기준으로 출력
    - 각 라인에 대해 parse_line() 결과의 (op,args)별로 1줄 출력
    - 인코딩은 encode_from_decoded()를 사용하여 (op4,dst4,arg8) 근사치로 계산

    출력 형식 예:
        [SRC] a = a - 1
          SUBI a, 1            | 0x71 0x01 | 0111 0001 0000 0001
    """

    src_lines = preprocess_program(lines) if preprocess else list(lines)

    for raw in src_lines:
        s = (raw or "").rstrip("\n")
        if not s:
            continue
        if debug:
            print(f"[SRC] {s}")

        try:
            ops = parse_line(s)
        except Exception:
            ops = []

        if not ops:
            # 그래도 한 줄의 근사 인코딩은 보여준다(NOP 등)
            approx = encode_from_source_line_fixed(s)
            if approx is not None and debug:
                b0, b1, bits = _encode_to_bytes(approx)
                print(f"  (no-ops)              | 0x{b0:02X} 0x{b1:02X} | {bits}")
            continue

        for op, args in ops:
            asm = _format_op(op, args)
            op_u = str(op).upper()
            # 실제 기계어 바이트를 생성하지 않는 디버깅/의사 명령(또는 라벨)은 별도 표기
            if op_u not in _MACHINE_OPS:
                if debug:
                    print(f"  {asm:<20} | No machine code generated")
                continue
            try:
                enc = encode_from_decoded((op, args))
                b0, b1, bits = _encode_to_bytes(enc)
                if debug:
                    print(f"  {asm:<20} | 0x{b0:02X} 0x{b1:02X} | {bits}")
            except Exception:
                # 인코딩 실패 시 ASM만 출력
                if debug:
                    print(f"  {asm}")


__all__ = [
    "print_listing",
]
