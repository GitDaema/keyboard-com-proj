#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include "CUESDK/CUESDK.framework/Headers/CUESDK.h"

void read_and_print_key_color(int deviceIndex, enum CorsairLedId ledId) {
    struct CorsairLedColor color;
    color.ledId = ledId;
    color.r = 0;
    color.g = 0;
    color.b = 0;

    if (CorsairGetLedsColorsByDeviceIndex(deviceIndex, 1, &color)) {
        printf("dKey %d color is: R=%d, G=%d, B=%d\n", ledId, color.r, color.g, color.b);
    } else {
        enum CorsairError error = CorsairGetLastError();
        printf("Error getting key color: %d\n", error);
    }
}

int main() {
    // 1. Perform protocol handshake
    struct CorsairProtocolDetails protocolDetails = CorsairPerformProtocolHandshake();
    if (protocolDetails.serverProtocolVersion == 0) {
        printf("Error: CUE is not running or was not found.\n");
        return 1;
    }

    // 2. Request exclusive lighting control
    if (!CorsairRequestControl(CAM_ExclusiveLightingControl)) {
        printf("Error requesting exclusive control.\n");
        return 1;
    }

    // 3. Set a high layer priority
    if (!CorsairSetLayerPriority(128)) {
        printf("Error setting layer priority.\n");
        return 1;
    }

    // 4. Get the keyboard device
    int keyboardIndex = -1;
    int deviceCount = CorsairGetDeviceCount();
    for (int i = 0; i < deviceCount; i++) {
        struct CorsairDeviceInfo *deviceInfo = CorsairGetDeviceInfo(i);
        if (deviceInfo && deviceInfo->type == CDT_Keyboard) {
            keyboardIndex = i;
            break;
        }
    }

    if (keyboardIndex == -1) {
        printf("Could not find a Corsair keyboard.\n");
        return 1;
    }

    // 5. Read the initial color of the 'A' key
    printf("Reading initial color of 'A' key...\n");
    read_and_print_key_color(keyboardIndex, CLK_A);

    // 6. Set the 'A' key to red
    printf("\nSetting the 'A' key to red...\n");
    struct CorsairLedColor ledColor;
    ledColor.ledId = CLK_A;
    ledColor.r = 255;
    ledColor.g = 0;
    ledColor.b = 0;

    if (!CorsairSetLedsColorsBufferByDeviceIndex(keyboardIndex, 1, &ledColor) || !CorsairSetLedsColorsFlushBuffer()) {
        enum CorsairError error = CorsairGetLastError();
        printf("Error setting color: %d\n", error);
        return 1;
    }
    printf("Set color command sent.\n");

    usleep(3000000); // 0.1초 대기

    // 7. Read the color of the 'A' key again
    printf("\nReading color of 'A' key after setting...\n");
    read_and_print_key_color(keyboardIndex, CLK_A);

    printf("\nPress Enter to exit and reset the color.\n");
    getchar();

    // 8. Reset the color and release control
    printf("Resetting color and releasing control...\n");
    ledColor.r = 0;
    ledColor.g = 0;
    ledColor.b = 0;
    CorsairSetLedsColorsBufferByDeviceIndex(keyboardIndex, 1, &ledColor);
    CorsairSetLedsColorsFlushBuffer();

    CorsairReleaseControl(CAM_ExclusiveLightingControl);

    return 0;
}