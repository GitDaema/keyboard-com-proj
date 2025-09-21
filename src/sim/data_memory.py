# sim/data_memory.py
class DataMemory:
    """변수 저장소 (signed 8비트: -128..127)"""
    def __init__(self) -> None:
        # 내부적으로도 -128..127 범위의 정수를 보관
        self.vars: dict[str, int] = {}

    @staticmethod
    def _wrap_s8(x: int) -> int:
        """임의의 정수를 signed 8비트로 래핑: -128..127"""
        return ((int(x) + 128) & 0xFF) - 128

    def get(self, name: str) -> int:
        """저장된 값을 -128..127로 반환 (없으면 0)"""
        return self._wrap_s8(self.vars.get(name, 0))

    def set(self, name: str, val: int) -> None:
        """입력값을 -128..127로 래핑하여 저장"""
        self.vars[name] = self._wrap_s8(val)