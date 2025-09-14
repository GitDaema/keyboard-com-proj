# -*- coding: utf-8 -*-
"""
OpenRGB 서버(127.0.0.1:6742)에 연결하여
키보드 ESC 키 LED 색상을 바꾸는 최소 예제 (openrgb-python 0.3.5 호환).

실행 전:
1) OpenRGB.exe --server --startminimized 로 켜두기
2) iCUE / Razer Synapse 등 종료
3) venv 활성화 후 실행
"""

import time
import os, json
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from keyboard_map import RGBLabelController

def main():
    # 1) 서버 연결 (이 버전은 host/timeout 키워드 없음)
    client = OpenRGBClient(
        address="127.0.0.1",
        port=6742,
        name="K70Demo",
        # protocol_version=None  # 필요 시 명시 가능
    )

    # 2) 키보드 장치 찾기
    #   - 일부 버전에선 client.devices 대신 client.get_devices()로 갱신해야 할 때가 있음
    devices = getattr(client, "devices", None) or client.get_devices()
    keyboards = []
    for d in devices:
        # d.type이 Enum일 수도 있고, 문자열일 수도 있으므로 안전하게 처리
        dtype = getattr(d.type, "name", str(d.type)).lower()
        if dtype == "keyboard":
            keyboards.append(d)

    if not keyboards:
        print("키보드 장치를 찾지 못했습니다. OpenRGB에서 장치 인식 확인 + 다른 RGB 앱 종료!")
        return

    kb = keyboards[0]
    print(f"연결된 키보드: {kb.name}, LED 개수: {len(kb.leds)}")

    # (선택) direct 모드 시도 — 일부 모델에서 개별 LED 제어에 필요할 수 있음(없으면 무시됨)
    try:
        kb.set_mode("direct")
    except Exception:
        pass

    # 3) ESC LED 찾기
    km = RGBLabelController(client, json_path=os.path.join(os.path.dirname(__file__), "maps", "Corsair K70 RGB TKL_leds.json"))
        
    # 4) 색상 순환
    for c in (RGBColor(255,0,0), RGBColor(0,255,0), RGBColor(0,0,255), RGBColor(0,0,0)):
        ok = km.set("esc", c)   # ← 라벨로 지정
        print("ESC ->", c, "OK" if ok else "MISS")
        time.sleep(0.8)

    print("완료")

if __name__ == "__main__":
    main()
