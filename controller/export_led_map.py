# -*- coding: utf-8 -*-
import json, csv, os
from openrgb import OpenRGBClient

OUT_DIR = os.path.join(os.path.dirname(__file__), "maps")
os.makedirs(OUT_DIR, exist_ok=True)

def main():
    client = OpenRGBClient(address="127.0.0.1", port=6742, name="MapExport")
    devices = getattr(client, "devices", None) or client.get_devices()
    kb = next((d for d in devices if getattr(d.type, "name", str(d.type)).lower()=="keyboard"), None)
    if not kb:
        raise SystemExit("키보드 장치를 찾지 못했습니다. OpenRGB에서 인식 상태 확인!")

    rows = []
    for idx, led in enumerate(kb.leds):
        rows.append({
            "index": idx,
            "name_raw": led.name or "",
            # 필요시 좌표/존 등 추가 (모델마다 없을 수 있음)
            # "zone": getattr(led, "zone", None),
        })

    # CSV
    csv_path = os.path.join(OUT_DIR, f"{kb.name}_leds.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["index","name_raw"])
        w.writeheader()
        w.writerows(rows)

    # JSON (기본 맵)
    json_path = os.path.join(OUT_DIR, f"{kb.name}_leds.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"keyboard": kb.name, "leds": rows}, f, ensure_ascii=False, indent=2)

    print(f"[OK] CSV 저장: {csv_path}")
    print(f"[OK] JSON 저장: {json_path}")

if __name__ == "__main__":
    main()