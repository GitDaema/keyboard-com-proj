# Keyboard COM Project

This project is a Python-based tool for controlling keyboard RGB lighting. It uses the `openrgb-python` library to communicate with an OpenRGB server, allowing users to programmatically change the colors of individual keys.

---

# 키보드 COM 프로젝트

이 프로젝트는 키보드 RGB 조명을 제어하기 위한 Python 기반 도구입니다. `openrgb-python` 라이브러리를 사용하여 OpenRGB 서버와 통신하며, 사용자가 프로그래밍 방식으로 개별 키의 색상을 변경할 수 있도록 합니다.

---

## 🇬🇧 English

### Features

*   Control individual key colors on your RGB keyboard.
*   Map human-readable key labels (e.g., "esc", "f1") to their corresponding LED indices.
*   Extensible design for adding support for new keyboard layouts.

### Project Structure

*   `controller/`: Contains the core Python scripts for controlling the keyboard.
    *   `main.py`: The main script that connects to the OpenRGB server and runs a demo sequence.
    *   `keyboard_map.py`: A module that maps human-readable key labels to their corresponding LED indices.
    *   `maps/`: Contains JSON files with LED layout information for specific keyboard models.
*   `scripts/`: Contains shell scripts for running the application.
    *   `run_demo_windows.sh`: A script for running the demo on Windows.
*   `requirements.txt`: Lists the Python dependencies for the project.

### Getting Started

#### Prerequisites

*   Python 3.6+
*   OpenRGB application

#### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-username/keyboard-com-proj.git
    ```
2.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

#### Usage

1.  Start the OpenRGB application with the server enabled.
2.  Run the demo script:
    ```bash
    ./scripts/run_demo_windows.sh
    ```
    Alternatively, you can run the main script directly:
    ```bash
    python controller/main.py
    ```
**Note:** Before running the script, make sure that the OpenRGB server is running and that any other RGB control software (e.g., iCUE, Razer Synapse) is closed.

### Development Conventions

*   The project uses a Python virtual environment (`.venv`) to manage dependencies.
*   The code is written in Python and follows standard Python coding conventions.
*   The `keyboard_map.py` module provides a clear and extensible way to add support for new keyboard layouts.
*   The use of shell scripts for automation simplifies the process of running the application.

---

## 🇰🇷 한국어

### 주요 기능

*   RGB 키보드의 개별 키 색상 제어
*   사람이 읽을 수 있는 키 라벨("esc", "f1" 등)을 해당 LED 인덱스에 매핑
*   새로운 키보드 레이아웃 지원을 위한 확장 가능한 디자인

### 프로젝트 구조

*   `controller/`: 키보드 제어를 위한 핵심 Python 스크립트를 포함합니다.
    *   `main.py`: OpenRGB 서버에 연결하고 데모 시퀀스를 실행하는 메인 스크립트입니다.
    *   `keyboard_map.py`: 사람이 읽을 수 있는 키 라벨을 해당 LED 인덱스에 매핑하는 모듈입니다.
    *   `maps/`: 특정 키보드 모델에 대한 LED 레이아웃 정보가 포함된 JSON 파일이 있습니다.
*   `scripts/`: 애플리케이션 실행을 위한 셸 스크립트를 포함합니다.
    *   `run_demo_windows.sh`: Windows에서 데모를 실행하기 위한 스크립트입니다.
*   `requirements.txt`: 프로젝트의 Python 의존성 목록입니다.

### 시작하기

#### 요구 사항

*   Python 3.6 이상
*   OpenRGB 애플리케이션

#### 설치

1.  리포지토리 복제:
    ```bash
    git clone https://github.com/your-username/keyboard-com-proj.git
    ```
2.  의존성 설치:
    ```bash
    pip install -r requirements.txt
    ```

#### 사용법

1.  서버가 활성화된 상태로 OpenRGB 애플리케이션을 시작합니다.
2.  데모 스크립트 실행:
    ```bash
    ./scripts/run_demo_windows.sh
    ```
    또는 메인 스크립트를 직접 실행할 수도 있습니다:
    ```bash
    python controller/main.py
    ```
**참고:** 스크립트를 실행하기 전에 OpenRGB 서버가 실행 중이고 다른 RGB 제어 소프트웨어(예: iCUE, Razer Synapse)가 닫혀 있는지 확인하십시오.

### 개발 컨벤션

*   이 프로젝트는 Python 가상 환경(`.venv`)을 사용하여 의존성을 관리합니다.
*   코드는 Python으로 작성되었으며 표준 Python 코딩 컨벤션을 따릅니다.
*   `keyboard_map.py` 모듈은 새로운 키보드 레이아웃을 쉽게 추가할 수 있도록 명확하고 확장 가능한 방법을 제공합니다.
*   자동화를 위한 셸 스크립트 사용은 애플리케이션 실행 프로세스를 단순화합니다.