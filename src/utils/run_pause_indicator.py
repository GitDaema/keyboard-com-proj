from openrgb.utils import RGBColor
from rgb_controller import set_key_color
import utils.color_presets as cp

# Single-key RUN/PAUSE indicator on `grave` key
# ON = RUN (green), OFF = PAUSE (black)
_LABEL = "grave"
_RUN_ON: RGBColor = cp.GREEN
_RUN_OFF: RGBColor = cp.BLACK

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

