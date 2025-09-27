from typing import Optional, List, Dict, Tuple, Any
from sim.parser import parse_line

Op = Tuple[str, tuple[Any, ...]]


class ProgramMemory:
    """
    Program storage with label addressing that does not consume
    addresses for label-only lines. Labels map to the next executable
    line index.
    """

    def __init__(self) -> None:
        # Raw source lines as loaded (may include labels)
        self.lines: List[str] = []
        # Executable lines with label-only lines removed
        self.exec_lines: List[str] = []
        # Label name -> executable address (index into exec_lines)
        self.labels: Dict[str, int] = {}
        # Cache for parsed ops per executable line index
        self._ops_cache: Dict[int, List[Op]] = {}

    def load_program(self, lines: List[str]) -> None:
        self.lines = [ln.rstrip("\n\r") for ln in lines]
        self._rebuild_compacted()
        self._ops_cache.clear()

    def fetch(self, pc: int) -> Optional[str]:
        if 0 <= pc < len(self.exec_lines):
            return self.exec_lines[pc]
        return None

    def size(self) -> int:
        return len(self.exec_lines)

    def get_label_addr(self, name: str) -> Optional[int]:
        return self.labels.get(name)

    def get_ops(self, pc: int) -> List[Op]:
        """Return parsed ops for the executable line at pc (cached)."""
        if pc not in self._ops_cache:
            line = self.fetch(pc) or ""
            self._ops_cache[pc] = parse_line(line)
        return self._ops_cache[pc]

    def _rebuild_compacted(self) -> None:
        """Build exec_lines and label mapping.
        Label-only lines do not take an address; labels map to the next
        executable line index.
        """
        self.exec_lines = []
        self.labels.clear()
        for raw in self.lines:
            s = (raw or "").strip()
            # Label-only line: "name:" (colon only at the end)
            if s.endswith(":") and (":" not in s[:-1]):
                name = s[:-1].strip()
                if name:
                    # First occurrence wins (simple rule)
                    self.labels.setdefault(name, len(self.exec_lines))
                continue  # do not include label-only line in exec_lines
            # Keep all other lines (including empty, treated as NOP)
            self.exec_lines.append(raw)

