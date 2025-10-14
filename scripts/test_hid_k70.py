import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.rgb_controller import RgbController
from src.utils.color_presets import RED, GREEN, BLUE, BLACK

def main():
    """
    Initializes the controller with the DirectHIDBackend and tests setting a few
    key colors.
    """
    if os.environ.get('RGB_BACKEND') != 'hid':
        print("Error: This script is intended to be run with the HID backend.")
        print("Please set the environment variable: $env:RGB_BACKEND='hid'")
        sys.exit(1)

    print("Initializing RgbController with DirectHIDBackend...")
    controller = RgbController(device_name="Corsair K70 RGB TKL")
    
    print("Testing key color setting...")
    
    keys_to_test = {
        "esc": RED,
        "f1": GREEN,
        "f2": BLUE
    }

    try:
        # Set initial colors
        for key_name, color in keys_to_test.items():
            print(f"Setting {key_name} to {color.name}...")
            controller.set_led(key_name, color)
            time.sleep(0.5)

        print("\nTest sequence complete. Keys should be colored.")
        print("Press Ctrl+C to exit and turn off LEDs.")

        # Keep colors on until user exits
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting. Turning off test keys...")
        for key_name in keys_to_test.keys():
            controller.set_led(key_name, BLACK)
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Attempting to turn off test keys...")
        for key_name in keys_to_test.keys():
            try:
                controller.set_led(key_name, BLACK)
            except Exception as final_e:
                print(f"Could not turn off {key_name}: {final_e}")

if __name__ == "__main__":
    main()
