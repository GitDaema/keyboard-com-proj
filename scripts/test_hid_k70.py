import os, sys, time
sys.path.insert(0, 'src')

# Force HID backend
os.environ['RGB_BACKEND'] = 'hid'

import rgb_controller as rc
from rgb_types import RGBColor


def main():
    print('[TEST] Connecting...')
    rc.connect()
    time.sleep(0.2)
    print('[TEST] Init all keys (black) ...')
    rc.init_all_keys()
    time.sleep(0.1)

    print('[TEST] ESC -> (255,0,0)')
    rc.set_key_color('esc', RGBColor(255,0,0))
    time.sleep(0.5)

    print('[TEST] F1 -> (0,255,0), F2 -> (0,0,255)')
    rc.set_key_color('f1', RGBColor(0,255,0))
    rc.set_key_color('f2', RGBColor(0,0,255))
    time.sleep(1.0)

    print('[TEST] Done. Colors should be visible if HID config is correct.')


if __name__ == '__main__':
    main()