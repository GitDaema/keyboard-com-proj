# Keyboard COM Project

This project is a Python-based tool for controlling keyboard RGB lighting. It uses the `openrgb-python` library to communicate with an OpenRGB server, allowing users to programmatically change the colors of individual keys.

## Features

*   Control individual key colors on your RGB keyboard.
*   Map human-readable key labels (e.g., "esc", "f1") to their corresponding LED indices.
*   Extensible design for adding support for new keyboard layouts.

## Getting Started

### Prerequisites

*   Python 3.6+
*   OpenRGB application

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-username/keyboard-com-proj.git
    ```
2.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Usage

1.  Start the OpenRGB application with the server enabled.
2.  Run the demo script:
    ```bash
    ./scripts/run_demo_windows.sh
    ```

---

# 키보드 COM 프로젝트

이 프로젝트는 키보드 RGB 조명을 제어하기 위한 Python 기반 도구입니다. `openrgb-python` 라이브러리를 사용하여 OpenRGB 서버와 통신하며, 사용자가 프로그래밍 방식으로 개별 키의 색상을 변경할 수 있도록 합니다.

## 주요 기능

*   RGB 키보드의 개별 키 색상 제어
*   사람이 읽을 수 있는 키 라벨("esc", "f1" 등)을 해당 LED 인덱스에 매핑
*   새로운 키보드 레이아웃 지원을 위한 확장 가능한 디자인

## 시작하기

### 요구 사항

*   Python 3.6 이상
*   OpenRGB 애플리케이션

### 설치

1.  리포지토리 복제:
    ```bash
    git clone https://github.com/your-username/keyboard-com-proj.git
    ```
2.  의존성 설치:
    ```bash
    pip install -r requirements.txt
    ```

### 사용법

1.  서버가 활성화된 상태로 OpenRGB 애플리케이션을 시작합니다.
2.  데모 스크립트 실행:
    ```bash
    ./scripts/run_demo_windows.sh
    ```
