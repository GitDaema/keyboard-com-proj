# Project Overview

This project is a Python-based tool for controlling keyboard RGB lighting. It uses the `openrgb-python` library to communicate with an OpenRGB server, allowing users to programmatically change the colors of individual keys.

The project is structured as follows:

*   `controller/`: Contains the core Python scripts for controlling the keyboard.
    *   `main.py`: The main script that connects to the OpenRGB server and runs a demo sequence.
    *   `keyboard_map.py`: A module that maps human-readable key labels (e.g., "esc", "f1") to their corresponding LED indices.
    *   `maps/`: Contains JSON files with LED layout information for specific keyboard models.
*   `scripts/`: Contains shell scripts for running the application.
    *   `run_demo_windows.sh`: A script for running the demo on Windows.
*   `requirements.txt`: Lists the Python dependencies for the project.

# Building and Running

To run this project, you will need to have Python and the `openrgb-python` library installed. You will also need to have the OpenRGB application running with the server enabled.

**1. Install Dependencies:**

```bash
pip install -r requirements.txt
```

**2. Run the Demo:**

The `scripts/run_demo_windows.sh` script provides a convenient way to run the demo on Windows. It will automatically start the OpenRGB server and then execute the main controller script.

```bash
./scripts/run_demo_windows.sh
```

Alternatively, you can run the main script directly:

```bash
python controller/main.py
```

**Note:** Before running the script, make sure that the OpenRGB server is running and that any other RGB control software (e.g., iCUE, Razer Synapse) is closed.

# Development Conventions

*   The project uses a Python virtual environment (`.venv`) to manage dependencies.
*   The code is written in Python and follows standard Python coding conventions.
*   The `keyboard_map.py` module provides a clear and extensible way to add support for new keyboard layouts.
*   The use of shell scripts for automation simplifies the process of running the application.
