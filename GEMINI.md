# Project Overview

This project is a Python-based 8-bit CPU and ISA (Instruction Set Architecture) visualizer that uses a keyboard's RGB lighting to display the CPU's internal state in real-time. It leverages the `openrgb-python` library to communicate with an OpenRGB server, turning the keyboard into a hardware debugger and educational tool.

The state of the CPU, including registers, flags, program counter (PC), and instruction register (IR), is mapped to the colors of individual keys.

The project is structured as follows:

*   `src/`: Contains the core Python source code.
    *   `main.py`: The main entry point that initializes the controller, configures the CPU, and runs the demo program.
    *   `rgb_controller.py`: Manages the connection to the OpenRGB server and provides an API for setting key colors.
    *   `sim/`: The CPU simulator components.
        *   `cpu.py`: The main CPU execution loop.
        *   `assembler.py`: Assembles the custom high-level language into a 2-byte ISA.
        *   `parser.py`: Parses the high-level language, supporting features like `IF/THEN/ELSE` blocks.
        *   `data_memory_rgb_visual.py`: Visualizes memory values on the keyboard and reads them back by sampling LED colors.
    *   `utils/`: Helper modules for keyboard mapping, color presets, and visualizing specific CPU parts (PC, IR, flags, etc.).
*   `data/`: Contains data files.
    *   `maps/`: JSON and CSV files with LED layout information for specific keyboard models.
*   `scripts/`: Contains shell scripts for running the application.
    *   `run_demo_windows.sh`: A script for running the demo on Windows, which can automatically start the OpenRGB server.
*   `requirements.txt`: Lists the Python dependencies for the project.

# Building and Running

To run this project, you need Python (3.9+ recommended) and the OpenRGB application.

**1. Install Dependencies:**

It is recommended to use a Python virtual environment.

```bash
# Create and activate a virtual environment
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**2. Run the Demo:**

Before running, ensure the OpenRGB application is running with the server active, and close any other vendor-specific RGB control software (e.g., iCUE, Razer Synapse).

The `scripts/run_demo_windows.sh` script provides the most convenient way to run the demo on Windows, as it can automatically start the OpenRGB server for you.

```bash
# Recommended for Windows
./scripts/run_demo_windows.sh
```

Alternatively, you can start the OpenRGB server manually and then run the main script directly:

```bash
# Run the main script (after ensuring OpenRGB server is running)
python src/main.py
```

# Development and Customization

*   **CPU and Language:** The simulator executes a custom high-level language which is pre-processed and assembled into a 2-byte ISA. The language supports variables, arithmetic, and control flow. See `LANGUAGE_SPEC_KO.txt` and `ISA_ENCODING_KO.txt` for details.
*   **Demo Program:** The demo program executed by the CPU is hardcoded as a list of strings in `src/main.py`. You can modify this list to experiment with the CPU's capabilities.
*   **Keyboard Mapping:** The project is configured for a `Corsair K70 RGB TKL` by default. To use a different keyboard:
    1.  Run `python src/utils/export_led_map.py` to generate a new layout JSON for your keyboard.
    2.  Update the `map_path` variable in `src/rgb_controller.py` to point to your new JSON file.