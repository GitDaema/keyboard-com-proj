from openrgb.utils import RGBColor

RED         = RGBColor(255,  0,  0)
DARK_RED    = RGBColor(150, 0, 0)
ORANGE      = RGBColor(255, 149,   5)
YELLOW      = RGBColor(255, 234,   0)
GREEN       = RGBColor(  0, 255,  0)
BLUE        = RGBColor(  0, 102, 204)
PURPLE      = RGBColor(170,   0, 170)
PINK        = RGBColor(255, 105, 180)
WHITE       = RGBColor(255, 255, 255)
BLACK       = RGBColor(  0,   0,   0)

HEX_COLORS = {
    0x0: RGBColor(0, 0, 0),          # Black

    # 1~7: Dark ROYGBIV
    0x1: RGBColor(128, 0,   0),      # Dark Red
    0x2: RGBColor(128, 64,  0),      # Dark Orange
    0x3: RGBColor(128,110,  0),      # Dark Yellow
    0x4: RGBColor(0, 110,  0),       # Dark Green
    0x5: RGBColor(0,  60, 128),      # Dark Blue
    0x6: RGBColor(38,  0,  65),      # Dark Indigo
    0x7: RGBColor(74,  0, 105),      # Dark Violet

    # 8~14: Bright ROYGBIV
    0x8:  RGBColor(255, 0,   0),     # Bright Red
    0x9:  RGBColor(255,128,  0),     # Bright Orange
    0xA:  RGBColor(255,220,  0),     # Bright Yellow
    0xB:  RGBColor(0,  220,  0),     # Bright Green
    0xC:  RGBColor(0,  120,255),     # Bright Blue
    0xD:  RGBColor(75,   0,130),     # Bright Indigo
    0xE:  RGBColor(148,  0,211),     # Bright Violet

    0xF: RGBColor(255,255,255),      # White
}