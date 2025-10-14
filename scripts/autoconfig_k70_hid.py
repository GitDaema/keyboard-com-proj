import hid
import json
import os
import time

# --- Configuration ---
TARGET_VID = 0x1B1C
# PID can vary, so we don't filter on it initially
# TARGET_PID = 0x1B59 
DEVICE_NAME_FILTER = "K70"

# The key we will flash to test the configuration
TEST_KEY_NAME = "Key: Escape"
TEST_KEY_LED_ID = 10 # From Corsair K70 RGB TKL_leds.json

# Path to save the final configuration
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_PATH = os.path.join(ROOT_DIR, "data", "devices", "corsair_k70_tkl_hid.json")

# --- Search Space for HID commands ---
# This defines the different byte combinations the script will try.
# Based on public information, Corsair uses report IDs and specific prologues.

# Report IDs to try sending the data on
REPORT_IDS = [0x00, 0x07]

# Prologues for the per-key command (e.g., [Report ID, Command ID, ...])
PER_KEY_PROLOGUES = [
    [0x01],         # Command ID 1
    [0x01, 0x01],   # Command ID 1, sub ID 1
    [0x07, 0x01],   # Report 7, Command 1
]

# Prologues for the commit command (to apply the color change)
COMMIT_PROLOGUES = [
    [0x02],         # Command ID 2
    [0x07, 0x02],   # Report 7, Command 2
]

# The number of bytes in the main part of the per-key command
# (usually led_id, r, g, b)
BODY_LENS = [4] # led_id (1), r (1), g (1), b (1)

# --- Main Script ---

def find_and_configure_device():
    """
    Scans for the target HID device and attempts to find a working lighting protocol
    by iterating through a predefined search space of commands.
    """
    print("Searching for Corsair K70 HID devices...")
    
    found_devices = []
    for device_dict in hid.enumerate():
        if device_dict["vendor_id"] == TARGET_VID and DEVICE_NAME_FILTER in device_dict["product_string"]:
            found_devices.append(device_dict)

    if not found_devices:
        print(f"Error: No Corsair device with VID {hex(TARGET_VID)} and name containing '{DEVICE_NAME_FILTER}' found.")
        print("Please ensure your keyboard is connected and not exclusively controlled by other software (like iCUE).")
        return

    print(f"Found {len(found_devices)} matching device entries. Probing each...")

    for device_info in found_devices:
        print(f"\n--- Probing Device ---")
        print(f"  Path: {device_info['path'].decode()}")
        print(f"  Product: {device_info['product_string']}")
        print(f"  Interface: {device_info['interface_number']}")
        print(f"  Usage Page: {hex(device_info['usage_page'])}\n")

        # The interesting interfaces are typically not interface 0
        if device_info['interface_number'] == 0:
            print("  Skipping interface 0 (usually standard keyboard input).")
            continue

        try:
            h = hid.device()
            h.open_path(device_info['path'])
            print(f"  Successfully opened device on interface {device_info['interface_number']}.")

            # Now, iterate through the search space
            if try_configurations(h, device_info):
                print("\nConfiguration successful!")
                h.close()
                return # Exit after first success
            
            h.close()

        except Exception as e:
            print(f"  Could not open or test device on this interface: {e}")

    print("\nConfiguration failed. No working HID command set found in the search space.")

def try_configurations(h, device_info):
    """
    Iterates through the search space of commands on an open HID device.
    """
    for report_id in REPORT_IDS:
        for per_key_prologue in PER_KEY_PROLOGUES:
            for commit_prologue in COMMIT_PROLOGUES:
                for body_len in BODY_LENS:
                    
                    # Construct the config for this attempt
                    config = {
                        "report_id": report_id,
                        "per_key_prologue": per_key_prologue,
                        "commit_prologue": commit_prologue,
                        "body_len": body_len
                    }

                    print(f"  Trying config: ReportID={hex(report_id)}, PerKey={bytes(per_key_prologue).hex()}, Commit={bytes(commit_prologue).hex()}...")

                    # Send the command to set ESC to RED
                    if send_test_command(h, config, (255, 0, 0)):
                        
                        # Ask user for confirmation
                        response = input("  ? Did the 'ESC' key turn RED? (y/n): ").lower().strip()

                        # Turn key off regardless of response
                        send_test_command(h, config, (0, 0, 0))

                        if response == 'y':
                            print("  Success! Found working configuration.")
                            save_configuration(device_info, config)
                            return True
    return False

def send_test_command(h, config, color):
    """
    Sends a single key color command to the device based on the current test config.
    """
    r, g, b = color
    try:
        # Per-Key command
        per_key_report = bytearray()
        if config["report_id"] != 0x00:
             per_key_report.append(config["report_id"])
        per_key_report.extend(config["per_key_prologue"])
        per_key_report.extend([TEST_KEY_LED_ID, r, g, b])
        # Pad to 64 bytes (typical for Corsair)
        per_key_report.extend([0] * (64 - len(per_key_report)))
        h.write(per_key_report)
        time.sleep(0.05)

        # Commit command
        commit_report = bytearray()
        if config["report_id"] != 0x00:
            commit_report.append(config["report_id"])
        commit_report.extend(config["commit_prologue"])
        # Pad to 64 bytes
        commit_report.extend([0] * (64 - len(commit_report)))
        h.write(commit_report)
        time.sleep(0.05)

        return True
    except Exception as e:
        print(f"    Error sending HID command: {e}")
        return False

def save_configuration(device_info, found_config):
    """
    Saves the working configuration to the JSON file.
    """
    print(f"Saving configuration to {CONFIG_PATH}...")
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    # Prepare the final JSON structure
    output_config = {
        "vid": hex(device_info["vendor_id"]),
        "pid": hex(device_info["product_id"]),
        "device_name": device_info["product_string"],
        "usage_page": hex(device_info["usage_page"]),
        "interface_number": device_info["interface_number"],
        "report_id": found_config["report_id"],
        "per_key": {
            "prologue": bytes(found_config["per_key_prologue"]).hex(),
            "prologue_len": len(found_config["per_key_prologue"]),
            "body_len": found_config["body_len"],
            "epilogue": "",
            "epilogue_len": 0
        },
        "commit": {
            "prologue": bytes(found_config["commit_prologue"]).hex(),
            "prologue_len": len(found_config["commit_prologue"])
        }
    }

    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(output_config, f, indent=4)
        print("  Successfully saved.")
    except Exception as e:
        print(f"  Error saving configuration file: {e}")

if __name__ == "__main__":
    find_and_configure_device()