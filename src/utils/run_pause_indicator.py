from openrgb.utils import RGBColor
from rgb_controller import set_key_color
from utils.keyboard_presets import (
    RUN_PAUSE_LABEL,
    RUN_PAUSE_ON,
    RUN_PAUSE_OFF,
)

# Single-key RUN/PAUSE indicator using presets from keyboard_presets
_LABEL = RUN_PAUSE_LABEL
_RUN_ON: RGBColor = RGBColor(*RUN_PAUSE_ON)
_RUN_OFF: RGBColor = RGBColor(*RUN_PAUSE_OFF)

def run_on() -> None:
    try:
        set_key_color(_LABEL, _RUN_ON)
    except Exception:
        # Indicator is best-effort; ignore hardware errors
        pass

def run_off() -> None:
    try:
        set_key_color(_LABEL, _RUN_OFF)
    except Exception:
        # Indicator is best-effort; ignore hardware errors
        pass

def set_run(is_running: bool) -> None:
    if is_running:
        run_on()
    else:
        run_off()
