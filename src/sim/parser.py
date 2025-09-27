from typing import List, Tuple, Any

# Parser debug print toggle (default off)
PARSER_DEBUG = False

Op = Tuple[str, tuple[Any, ...]]

def parse_line(line: str) -> List[Op]:
    s = line.strip()
    if not s or s.startswith("#"):
        return [("NOP", ())]

    # 라벨: "name:" (콜론이 맨 끝에 하나만 있는 경우)
    if s.endswith(":") and (":" not in s[:-1]):
        name = s[:-1].strip()
        return [("LABEL", (name,))] if name else [("NOP", ())]

    up = s.upper()

    # 단일 토큰류
    if up == "HALT":
        return [("HALT", ())]
    if up == "NOP":
        return [("NOP", ())]
    if up == "ADD8":
        return [("ADD8", ())]
    if up == "SUB8":
        return [("SUB8", ())]
    if up == "PRINT_RES":         # ← 추가
        return [("PRINT_RES", ())]

    # --- PRINT 확장: "PRINT a + b"도 비트 경유 + PRINT_RES 로 ---
    if up.startswith("PRINT "):
        expr = s[6:].strip()
        # 1) 덧셈 표현식: UNPACK/LOAD → ADD8 → (RES에 결과) → PRINT_RES
        if "+" in expr:
            a, b = [t.strip() for t in expr.split("+", 1)]
            ops: List[Op] = []

            def emit_load_into(group: str, token: str):
                if _is_int_literal(token):
                    ops.append(("LOADI8_BITS", (group, _parse_int(token))))
                else:
                    ops.append(("UNPACK1" if group=="SRC1" else "UNPACK2", (token,)))

            emit_load_into("SRC1", a)
            emit_load_into("SRC2", b)
            ops.append(("ADD8", ()))
            # tmp 변수 없이 RES에서 직접 출력
            ops.append(("PRINT_RES", ()))
            return ops

        # 2) 단일 변수/리터럴: RES에 적재해놓고 바로 출력
        ops: List[Op] = []
        if _is_int_literal(expr):
            ops.append(("LOADI8_BITS", ("SRC1", _parse_int(expr))))
            ops.append(("COPYBITS", ("RES", "SRC1")))
        else:
            ops.append(("UNPACK1", (expr,)))
            ops.append(("COPYBITS", ("RES", "SRC1")))
        ops.append(("PRINT_RES", ()))
        return ops

    # --- 분기/점프/비교 ---
    if up.startswith("JMP "):
        label = s[4:].strip()
        return [("JMP", (label,))]
    if up.startswith("BEQ "):
        label = s[4:].strip()
        return [("BEQ", (label,))]
    if up.startswith("BNE "):
        label = s[4:].strip()
        return [("BNE", (label,))]
    # V(overflow) 기반 분기 (신규)
    if up.startswith("BVC "):
        label = s[4:].strip()
        return [("BVC", (label,))]
    if up.startswith("BVS "):
        label = s[4:].strip()
        return [("BVS", (label,))]
    # 하위 호환: C기반 표기(BCC/BCS)를 V로 해석
    if up.startswith("BCC "):
        label = s[4:].strip()
        return [("BCC", (label,))]
    if up.startswith("BCS "):
        label = s[4:].strip()
        return [("BCS", (label,))]
    if up.startswith("BMI "):
        label = s[4:].strip()
        return [("BMI", (label,))]
    if up.startswith("BPL "):
        label = s[4:].strip()
        return [("BPL", (label,))]

    # CMP/CMPI: 두 번째 피연산자가 '#'면 CMPI
    if up.startswith("CMP "):
        a, b = _split2(s[4:])
        if b.startswith("#"):
            return [("CMPI", (a, _parse_int(b[1:])))]
        return [("CMP", (a, b))]
    if up.startswith("CMPI "):
        a, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("CMPI", (a, _parse_int(imm[1:])))]
        return [("CMPI", (a, _parse_int(imm)))]

    # --- 저수준: MOV/ADD/ADDI/SUB/SUBI/비트/시프트 ---

    # MOV/MOVI: 두 번째가 즉시이면 MOVI
    if up.startswith("MOV "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("MOVI", (dst, _parse_int(src[1:])))]
        return [("MOV", (dst, src))]

    # ADD/ADDI
    if up.startswith("ADD "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("ADDI", (dst, _parse_int(src[1:])))]
        return [("ADD", (dst, src))]
    if up.startswith("ADDI "):
        dst, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("ADDI", (dst, _parse_int(imm[1:])))]
        return [("ADDI", (dst, _parse_int(imm)))]

    # SUB/SUBI
    if up.startswith("SUB "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("SUBI", (dst, _parse_int(src[1:])))]
        return [("SUB", (dst, src))]
    if up.startswith("SUBI "):
        dst, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("SUBI", (dst, _parse_int(imm[1:])))]
        return [("SUBI", (dst, _parse_int(imm)))]

    # 비트 연산
    if up.startswith("AND "):
        dst, src = _split2(s[4:])
        return [("AND", (dst, src))]
    if up.startswith("OR "):
        dst, src = _split2(s[3:])
        return [("OR", (dst, src))]
    if up.startswith("XOR "):
        dst, src = _split2(s[4:])
        return [("XOR", (dst, src))]

    # 시프트(단항) - SHR는 산술 시프트로 동작(부호 유지)
    if up.startswith("SHL "):
        dst = s[4:].strip()
        return [("SHL", (dst,))]
    if up.startswith("SHR "):
        dst = s[4:].strip()
        return [("SHR", (dst,))]
    
    # --- 비트 전용 마이크로옵 ---
    # UNPACK1 var  → var 값을 SRC1 8비트로
    # UNPACK2 var  → var 값을 SRC2 8비트로
    # UNPACK var, SRC1|SRC2
    if up.startswith("UNPACK1 "):
        var = s[len("UNPACK1 "):].strip()
        return [("UNPACK1", (var,))]
    if up.startswith("UNPACK2 "):
        var = s[len("UNPACK2 "):].strip()
        return [("UNPACK2", (var,))]
    if up.startswith("UNPACK "):
        a, b = _split2(s[len("UNPACK "):])
        return [("UNPACK", (a, b.upper()))]  # "SRC1"|"SRC2"

    # LOADI8_BITS group, #imm
    if up.startswith("LOADI8_BITS "):
        grp, imm = _split2(s[len("LOADI8_BITS "):])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("LOADI8_BITS", (grp.upper(), _parse_int(imm[1:])))]
        return [("LOADI8_BITS", (grp.upper(), _parse_int(imm)))]

    # CLEARBITS group
    if up.startswith("CLEARBITS "):
        grp = s[len("CLEARBITS "):].strip().upper()
        return [("CLEARBITS", (grp,))]

    # COPYBITS dst, src  (예: COPYBITS RES, SRC1)
    if up.startswith("COPYBITS "):
        dst, src = _split2(s[len("COPYBITS "):])
        return [("COPYBITS", (dst.upper(), src.upper()))]

    # PACK var   (RES 비트 → var에 패킹)
    if up.startswith("PACK "):
        var = s[len("PACK "):].strip()
        return [("PACK", (var,))]

    # --- 고수준 대입식(=)을 비트 마이크로옵으로 내림 ---
    if "=" in s:
        left, right = [t.strip() for t in s.split("=", 1)]
        ops: List[Op] = []

        def emit_load_into(group: str, token: str):
            """group: 'SRC1'|'SRC2'에 token(변수 또는 리터럴)을 적재"""
            if _is_int_literal(token):
                ops.append(("LOADI8_BITS", (group, _parse_int(token))))
            else:
                if group == "SRC1":
                    ops.append(("UNPACK1", (token,)))
                else:
                    ops.append(("UNPACK2", (token,)))

        # 덧셈 대입: x = a + b
        if "+" in right:
            a, b = [t.strip() for t in right.split("+", 1)]
            if a != "":  # 이항 연산 인식
                if PARSER_DEBUG:
                    print(f"[PARSER DEBUG] left='{left}', a='{a}', b='{b}', is_b_int={_is_int_literal(b)}")

                # 최적화: a = a + 5  →  ADDI a, 5
                if left == a and _is_int_literal(b):
                    return [("ADDI", (left, _parse_int(b)))]
                if left == b and _is_int_literal(a):
                    return [("ADDI", (left, _parse_int(a)))]

                # 일반적인 경우: c = a + b
                emit_load_into("SRC1", a)
                emit_load_into("SRC2", b)
                ops.append(("ADD8", ()))
                ops.append(("PACK", (left,)))
                return ops

        # 뺄셈 대입: x = a - b  
        if "-" in right:
            a, b = [t.strip() for t in right.split("-", 1)]
            if a != "":
                # 최적화: x = x - imm  → SUBI x, imm
                if left == a and _is_int_literal(b):
                    return [("SUBI", (left, _parse_int(b)))]
                # 최적화: x = x - y    → SUB x, y
                if left == a and not _is_int_literal(b):
                    return [("SUB", (left, b))]
                # 일반적인 경우: c = a - b (중간 비트 경유)
                emit_load_into("SRC1", a)
                emit_load_into("SRC2", b)
                ops.append(("SUB8", ()))
                ops.append(("PACK", (left,)))
                return ops

        # 단순 대입: x = y  또는 x = 5
        emit_load_into("SRC1", right)
        ops.append(("COPYBITS", ("RES", "SRC1")))  # RES ← SRC1
        ops.append(("PACK", (left,)))             # RES 패킹 → x
        return ops

    return [("NOP", ())]

# ---------------- helpers ----------------
def _split2(body: str) -> tuple[str, str]:
    parts = [t.strip() for t in body.split(",", 1)]
    if len(parts) != 2:
        return (body.strip(), "")
    return parts[0], parts[1]

def _is_int_literal(s: str) -> bool:
    try:
        int(s, 0)
        return True
    except:
        return False

def _parse_int(s: str) -> int:
    return int(s, 0)

# ---------------- high-level block preprocessing ----------------
def preprocess_program(lines: List[str]) -> List[str]:
    """멀티라인 블록(IF/ELSE/END)을 저수준 명령 시퀀스로 전개.
    - 지원 비교: ==, !=, <, >, <=, >= (signed)
    - 문법:
        IF <lhs> <op> <rhs> THEN
            ... (문장들)
        [ELSE]
            ... (문장들)
        END
    - 중첩 IF 지원.
    - 생성 라벨: __IF{n}_ELSE, __IF{n}_END, 필요 시 __IF{n}_V0, __IF{n}_CONT
    """

    def _is_imm_token(tok: str) -> bool:
        t = tok.strip()
        if t.startswith('#'):
            t = t[1:]
        return _is_int_literal(t)

    def _parse_if_header(s: str) -> tuple[str, str, str] | None:
        # s: 원본 라인(대소문자 무관). "IF ... THEN" 형태만 처리
        up = s.strip()
        if not up.upper().startswith('IF '):
            return None
        idx_then = up.upper().rfind(' THEN')
        if idx_then == -1:
            return None
        cond = up[3:idx_then].strip()  # IF 이후 ~ THEN 이전
        # 두 글자 연산자 우선 탐색
        for op in ("==", "!=", "<=", ">="):
            k = cond.find(op)
            if k != -1:
                lhs = cond[:k].strip()
                rhs = cond[k+len(op):].strip()
                return lhs, op, rhs
        # 단일 글자
        for op in ("<", ">"):
            k = cond.find(op)
            if k != -1:
                lhs = cond[:k].strip()
                rhs = cond[k+len(op):].strip()
                return lhs, op, rhs
        return None

    out: List[str] = []
    stack: List[dict[str, Any]] = []
    if_counter = 0

    def _emit_cmp_and_branch_false(lhs: str, op: str, rhs: str, else_label: str, base: str) -> None:
        # 비교 실행(CMP/CMPI) 후, 조건이 거짓일 때 else_label로 분기하는 시퀀스를 out에 추가
        is_imm = _is_imm_token(rhs)
        if is_imm:
            imm = rhs[1:] if rhs.strip().startswith('#') else rhs.strip()
            out.append(f"CMPI {lhs}, {imm}")
        else:
            out.append(f"CMP {lhs}, {rhs}")

        # Fast-path for comparisons against 0 using N/Z only
        try:
            if is_imm:
                v0 = _parse_int(imm)
                if op == '<' and v0 == 0:
                    # false when a >= 0 -> N=0
                    out.append(f"BPL {else_label}")
                    return
                if op == '>=' and v0 == 0:
                    # false when a < 0 -> N=1
                    out.append(f"BMI {else_label}")
                    return
                if op == '<=' and v0 == 0:
                    # false when a > 0 -> Z=0 and N=0
                    out.append(f"BEQ {base}_LE0_TRUE")  # Z=1 -> true path
                    out.append(f"BPL {else_label}")      # Z=0 & N=0 -> false
                    out.append(f"{base}_LE0_TRUE:")
                    return
                if op == '>' and v0 == 0:
                    # false when a <= 0 -> Z=1 or N=1
                    out.append(f"BMI {else_label}")      # N=1 -> false
                    out.append(f"BEQ {else_label}")      # Z=1 -> false
                    return
        except Exception:
            pass

        # 간단 케이스
        if op == '==':
            out.append(f"BNE {else_label}")
            return
        if op == '!=':
            out.append(f"BEQ {else_label}")
            return

        v0 = f"{base}_V0"
        cont = f"{base}_CONT"

        if op == '<':  # 거짓 = GE (N xor V == 0)
            out.append(f"BVC {v0}")
            out.append(f"BMI {else_label}")  # V=1,N=1 -> GE -> 거짓
            out.append(f"JMP {cont}")
            out.append(f"{v0}:")
            out.append(f"BPL {else_label}")  # V=0,N=0 -> GE -> 거짓
            out.append(f"{cont}:")
            return

        if op == '>=':  # 거짓 = LT
            out.append(f"BVC {v0}")
            out.append(f"BPL {else_label}")  # V=1,N=0 -> LT -> 거짓
            out.append(f"JMP {cont}")
            out.append(f"{v0}:")
            out.append(f"BMI {else_label}")  # V=0,N=1 -> LT -> 거짓
            out.append(f"{cont}:")
            return

        if op == '<=':  # 거짓 = GT (Z=0 and N xor V=0)
            out.append(f"BEQ {cont}")  # Z=1 -> 참 -> 통과
            out.append(f"BVC {v0}")
            out.append(f"BMI {else_label}")  # V=1,N=1 -> GE & Z=0 -> GT -> 거짓 분기
            out.append(f"JMP {cont}")
            out.append(f"{v0}:")
            out.append(f"BPL {else_label}")  # V=0,N=0 -> GE & Z=0 -> GT -> 거짓 분기
            out.append(f"{cont}:")
            return

        if op == '>':  # 거짓 = LE (Z=1 or LT)
            out.append(f"BEQ {else_label}")  # Z=1 -> LE -> 거짓 분기
            out.append(f"BVC {v0}")
            out.append(f"BPL {else_label}")  # V=1,N=0 -> LT -> 거짓 분기
            out.append(f"JMP {cont}")
            out.append(f"{v0}:")
            out.append(f"BMI {else_label}")  # V=0,N=1 -> LT -> 거짓 분기
            out.append(f"{cont}:")
            return

        # 미지원 연산자 안전장치: 거짓으로 간주하여 else로
        out.append(f"JMP {else_label}")

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i].rstrip('\n')
        s = raw.strip()
        up = s.upper()

        # ELSE 처리
        if up == 'ELSE' or up == 'ELSE:':
            if not stack:
                out.append(raw)
                i += 1
                continue
            frame = stack[-1]
            if frame.get('has_else', False):
                out.append(raw)
                i += 1
                continue
            out.append(f"JMP {frame['end_label']}")
            out.append(f"{frame['else_label']}:")
            frame['has_else'] = True
            i += 1
            continue

        # END/ENDIF 처리
        if up == 'END' or up == 'END IF' or up == 'ENDIF':
            if not stack:
                out.append(raw)
                i += 1
                continue
            frame = stack.pop()
            if not frame.get('has_else', False):
                out.append(f"{frame['else_label']}:")
            out.append(f"{frame['end_label']}:")
            i += 1
            continue

        # IF ... THEN 처리
        hdr = _parse_if_header(s)
        if hdr is not None:
            lhs, op, rhs = hdr
            base = f"__IF{if_counter}"
            else_label = f"{base}_ELSE"
            end_label = f"{base}_END"
            _emit_cmp_and_branch_false(lhs, op, rhs, else_label, base)
            stack.append({
                'base': base,
                'else_label': else_label,
                'end_label': end_label,
                'has_else': False,
            })
            if_counter += 1
            i += 1
            continue

        # 일반 라인은 그대로 전달
        out.append(raw)
        i += 1

    # 미닫힌 블록 정리(안전장치)
    while stack:
        frame = stack.pop()
        if not frame.get('has_else', False):
            out.append(f"{frame['else_label']}:")
        out.append(f"{frame['end_label']}:")

    return out
