# sim/data_memory.py
class DataMemory:
    """변수 저장소 (8비트 래핑)"""
    def __init__(self) -> None:
        self.vars: dict[str, int] = {}

    @staticmethod
    def _wrap8(x: int) -> int:
        return x & 0xFF

    def get(self, name: str) -> int:
        return self._wrap8(self.vars.get(name, 0))

    def set(self, name: str, val: int) -> None:
        self.vars[name] = self._wrap8(val)
