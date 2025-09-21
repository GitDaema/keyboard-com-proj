# sim/ir.py
from dataclasses import dataclass
from typing import Optional, Tuple, Any

@dataclass
class IR:
    raw: Optional[str] = None
    decoded: Optional[Tuple[str, tuple[Any, ...]]] = None

    def clear(self) -> None:
        self.raw = None
        self.decoded = None
