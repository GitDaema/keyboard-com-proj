# sim/program_memory.py
from typing import Optional, List, Dict
from sim.parser import parse_line  # ← 추가
from typing import Tuple, Any

Op = Tuple[str, tuple[Any, ...]]

class ProgramMemory:
    """
    소스 코드 라인 단위로 보관/Fetch + 라벨 테이블
    - 라벨 형식: "label:" (행의 처음~끝까지 콜론으로 끝나면 라벨로 간주)
    - 라벨은 그 라인의 인덱스를 가리킴(그 라인은 보통 NOP로 파싱되어 한 사이클 소비됨)
      * 최소 구현을 위해 라벨-전용 라인을 스킵하지 않고 남겨둠(간단/안전)
    """
    def __init__(self) -> None:
        self.lines: List[str] = []
        self.labels: Dict[str, int] = {}
        self._ops_cache: Dict[int, List[Op]] = {}  # ← 추가

    def load_program(self, lines: List[str]) -> None:
        self.lines = [ln.rstrip() for ln in lines]
        self._build_label_map()
        self._ops_cache.clear()  # ← 추가: 프로그램 로드시 캐시 초기화

    def fetch(self, pc: int) -> Optional[str]:
        if 0 <= pc < len(self.lines):
            return self.lines[pc]
        return None

    def size(self) -> int:
        return len(self.lines)

    def get_label_addr(self, name: str) -> Optional[int]:
        return self.labels.get(name)

    def get_ops(self, pc: int) -> List[Op]:
        """해당 라인의 파싱 결과를 캐시하여 반환"""
        if pc not in self._ops_cache:
            line = self.fetch(pc)
            self._ops_cache[pc] = parse_line(line if line is not None else "")
        return self._ops_cache[pc]

    def _build_label_map(self) -> None:
        self.labels.clear()
        for idx, raw in enumerate(self.lines):
            s = raw.strip()
            if s.endswith(":") and (":" not in s[:-1]):  # "name:" 형태만
                name = s[:-1].strip()
                if name:
                    # 같은 이름이 여러 번 나오면 첫 번째만 유효(간단 규칙)
                    self.labels.setdefault(name, idx)
