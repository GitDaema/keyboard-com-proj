import time
import sys

try:
    import hid  # hidapi wheel
except Exception:
    try:
        from pyhidapi import hid  # pyhidapi fallback
    except Exception as ex:
        print('[ERR] hid module not available:', ex)
        sys.exit(1)

VENDOR = 0x1B1C
PRODUCT = 0x1B73
TARGET_IFACES = {1, 2}  # from enumerate output
TARGET_USAGE_PAGE = 0xFF42  # 65346

# ESC LED index from map (Corsair K70 RGB TKL_leds.json shows 10)
ESC_INDEX = 10

INIT_CANDIDATES = [
    bytes.fromhex('07 00 00 00 00 00'),
    bytes.fromhex('09 00 00 00 00 00'),
]

REPORT_IDS = [7, 9, 14]
LENGTHS = [64, 65]
OFFSET_SETS = [
    {'index': 2, 'r': 5, 'g': 6, 'b': 7},
    {'index': 3, 'r': 6, 'g': 7, 'b': 8},
    {'index': 4, 'r': 7, 'g': 8, 'b': 9},
]
COMMIT = bytes.fromhex('07 01 00 00 00 00')


def open_targets():
    devs = []
    for d in hid.enumerate(VENDOR, PRODUCT):
        try:
            iface = d.get('interface_number')
            upage = d.get('usage_page')
            path = d.get('path')
        except Exception:
            continue
        if path is None:
            continue
        if int(upage or 0) != TARGET_USAGE_PAGE:
            continue
        if iface not in TARGET_IFACES:
            continue
        try:
            h = hid.device()
            h.open_path(path)
            try:
                h.set_nonblocking(True)
            except Exception:
                pass
            devs.append(h)
        except Exception:
            pass
    return devs


def send_both(dev, payload: bytes):
    # Try feature then output; ignore errors
    try:
        dev.send_feature_report(payload)
    except Exception:
        pass
    try:
        dev.write(payload)
    except Exception:
        pass


def try_combo(devs, rid, length, offs, color=(255, 0, 0)):
    buf = bytearray(max(1, int(length)))
    buf[0] = int(rid) & 0xFF
    # index and RGB
    idx = ESC_INDEX
    if 0 <= offs['index'] < len(buf):
        buf[offs['index']] = idx & 0xFF
    r, g, b = color
    for k, v in (('r', r), ('g', g), ('b', b)):
        pos = offs[k]
        if 0 <= pos < len(buf):
            buf[pos] = int(v) & 0xFF
    payload = bytes(buf)
    print(f"[TRY] rid={rid} len={length} offs={offs} -> ESC {color}")
    for d in devs:
        send_both(d, payload)
    time.sleep(0.15)
    for d in devs:
        send_both(d, COMMIT)
    time.sleep(0.2)


def main():
    devs = open_targets()
    if not devs:
        print('[ERR] No target HID interfaces (usage_page=0xFF42 iface 1/2).')
        sys.exit(2)
    print('[INFO] Opened', len(devs), 'devices')

    # Init sweep
    for init in INIT_CANDIDATES:
        print('[INIT]', init)
        for d in devs:
            send_both(d, init)
        time.sleep(0.2)

    # Per-key sweep (watch keyboard while it runs)
    for rid in REPORT_IDS:
        for ln in LENGTHS:
            for offs in OFFSET_SETS:
                try_combo(devs, rid, ln, offs, (255, 0, 0))
                try_combo(devs, rid, ln, offs, (0, 255, 0))
                try_combo(devs, rid, ln, offs, (0, 0, 255))

    # Close
    for d in devs:
        try:
            d.close()
        except Exception:
            pass
    print('[DONE] Probe finished. Note any combo that changed LEDs.')


if __name__ == '__main__':
    main()