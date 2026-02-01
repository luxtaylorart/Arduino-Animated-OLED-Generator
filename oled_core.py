# oled_core.py
import os
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from PIL import Image

APP_TITLE = "Lux Taylor Art / Arduino Animated OLED Generator V0.1"

@dataclass(frozen=True)
class BoardInfo:
    name: str
    flash_bytes: int

    i2c_sda: str
    i2c_scl: str
    spi_mosi: str
    spi_miso: str
    spi_sck: str

    default_cs: str
    default_dc: str
    default_rst: str

BOARDS = {
    "Seeeduino XIAO (SAMD21)": BoardInfo(
        name="Seeeduino XIAO (SAMD21)",
        flash_bytes=256 * 1024,
        i2c_sda="D4",
        i2c_scl="D5",
        spi_mosi="D10",
        spi_miso="D9",
        spi_sck="D8",
        default_cs="D7",
        default_dc="D2",
        default_rst="D3",
    ),
    "Arduino Nano": BoardInfo(
        name="Arduino Nano",
        flash_bytes=32 * 1024,
        i2c_sda="A4",
        i2c_scl="A5",
        spi_mosi="D11",
        spi_miso="D12",
        spi_sck="D13",
        default_cs="10",
        default_dc="9",
        default_rst="8",
    ),
    "Seeed XIAO ESP32C6": BoardInfo(
        name="Seeed XIAO ESP32C6",
        flash_bytes=4 * 1024 * 1024,
        i2c_sda="D4",
        i2c_scl="D5",
        spi_mosi="D10",
        spi_miso="D9",
        spi_sck="D8",
        default_cs="D7",
        default_dc="D2",
        default_rst="D3",
    ),
}

RESOLUTIONS = ["128x64", "128x32"]
PROTOCOLS = ["SPI", "I2C"]

THRESHOLD = 128
BITMAP_DRAW_MODE = "Horizontal 1bpp"

def find_first_int(s: str) -> Optional[int]:

    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def center_crop(im: Image.Image, target_w: int, target_h: int) -> Image.Image:

    w, h = im.size
    left = max(0, (w - target_w) // 2)
    top = max(0, (h - target_h) // 2)
    right = left + min(target_w, w)
    bottom = top + min(target_h, h)
    cropped = im.crop((left, top, right, bottom))

    if cropped.size != (target_w, target_h):
        out = Image.new("L", (target_w, target_h), 0)
        ox = (target_w - cropped.size[0]) // 2
        oy = (target_h - cropped.size[1]) // 2
        out.paste(cropped, (ox, oy))
        return out
    return cropped


def image_to_1bpp_horizontal_bytes(im: Image.Image, w: int, h: int, threshold: int = THRESHOLD) -> bytes:

    g = im.convert("L")

    bw = g.point(lambda p: 255 if p >= threshold else 0, mode="1")

    pixels = bw.load()
    out = bytearray()

    for y in range(h):
        byte = 0
        bit_count = 0
        for x in range(w):
            bit = 1 if pixels[x, y] else 0
            byte = (byte << 1) | bit
            bit_count += 1
            if bit_count == 8:
                out.append(byte & 0xFF)
                byte = 0
                bit_count = 0
        if bit_count != 0:

            byte = byte << (8 - bit_count)
            out.append(byte & 0xFF)

    return bytes(out)


def bytes_to_c_array(data: bytes, columns: int = 12) -> str:

    parts = [f"0x{b:02X}" for b in data]
    lines = []
    for i in range(0, len(parts), columns):
        lines.append(", ".join(parts[i:i + columns]))
    return ",\n  ".join(lines)


def safe_c_identifier(name: str) -> str:

    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base)
    if re.match(r"^\d", base):
        base = "img_" + base
    return base


def estimate_bitmap_bytes(frame_count: int, w: int, h: int) -> int:

    per_frame = (w * h) // 8
    ptrs = frame_count * 4
    return frame_count * per_frame + ptrs


def generate_bitmaps_h(frame_paths: List[str], w: int, h: int, per_frame_bytes: List[bytes]) -> str:
    lines = []
    lines.append("#pragma once")
    lines.append("#include <Arduino.h>")
    lines.append("")
    lines.append(f"// draw mode: {BITMAP_DRAW_MODE}, threshold: {THRESHOLD}")
    lines.append("")

    # Individual frames
    frame_names = []
    for idx, path in enumerate(frame_paths):
        ident = safe_c_identifier(path)
        ident = f"{ident}_{idx:03d}"
        frame_names.append(ident)
        lines.append(f"const uint8_t {ident}[] PROGMEM = {{")
        lines.append("  " + bytes_to_c_array(per_frame_bytes[idx]) + "")
        lines.append("};")
        lines.append("")

    # Pointer table
    lines.append("const uint8_t* const bmpArray[] PROGMEM = {")
    for ident in frame_names:
        lines.append(f"  {ident},")
    lines.append("};")
    lines.append("")
    lines.append(f"const int frameCount = {len(frame_paths)};")
    lines.append(f"const int frameWidth = {w};")
    lines.append(f"const int frameHeight = {h};")
    return "\n".join(lines)


def generate_sketch_ino(
    board_name: str,
    protocol: str,
    w: int,
    h: int,
    pin_cs: str,
    pin_dc: str,
    pin_rst: str,
    uniform_timing: bool,
    uniform_delay_ms: int,
    per_frame_delays: List[int],
) -> str:

    lines = []
    lines.append("// Arduino OLED Animator / Lux Taylor Art")
    lines.append(f"// board: {board_name}")
    lines.append(f"// protocol: {protocol}")
    lines.append("")
    if protocol == "SPI":
        lines.append("#define SSD1306_SPI_SPEED 8000000")
        lines.append("#include <SPI.h>")
    else:
        lines.append("#include <Wire.h>")
    lines.append("#include <Adafruit_GFX.h>")
    lines.append("#include <Adafruit_SSD1306.h>")
    lines.append('#include "bitmaps.h"')
    lines.append("")
    lines.append(f"#define SCREEN_WIDTH {w}")
    lines.append(f"#define SCREEN_HEIGHT {h}")
    lines.append("")

    if protocol == "SPI":
        lines.append(f"#define OLED_CS {pin_cs}")
        lines.append(f"#define OLED_DC {pin_dc}")
        lines.append(f"#define OLED_RESET {pin_rst}")
        lines.append("")
        lines.append("Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &SPI, OLED_DC, OLED_RESET, OLED_CS);")
    else:
        lines.append(f"#define OLED_RESET {pin_rst}")
        lines.append("#define OLED_I2C_ADDR 0x3C")
        lines.append("")
        lines.append("Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);")

    lines.append("")
    lines.append("// timing")
    if uniform_timing:

        d = int(uniform_delay_ms)
        if d <= 0:
            d = 1
        lines.append(f"const uint16_t frameDelayMs = {d};")
    else:
        delays_list = ", ".join(str(int(x)) for x in per_frame_delays)
        lines.append(f"const uint16_t frameDelaysMs[frameCount] = {{ {delays_list} }};")
    lines.append("unsigned long lastFrameTime = 0;")
    lines.append("int currentFrame = 0;")
    lines.append("")

    lines.append("static const uint8_t* getFramePtr(int idx) {")
    lines.append("  return (const uint8_t*)pgm_read_ptr(&bmpArray[idx]);")
    lines.append("}")
    lines.append("")

    lines.append("void setup() {")
    if protocol == "I2C":
        lines.append("  Wire.begin();")
        lines.append("  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {")
    else:
        lines.append("  if (!display.begin(SSD1306_SWITCHCAPVCC)) {")
    lines.append("    for(;;) {}  // halt if OLED not found")
    lines.append("  }")
    lines.append("")
    lines.append("  display.clearDisplay();")
    lines.append("  display.drawBitmap(0, 0, getFramePtr(0), SCREEN_WIDTH, SCREEN_HEIGHT, WHITE);")
    lines.append("  display.display();")
    lines.append("}")
    lines.append("")

    lines.append("void loop() {")
    lines.append("  if (frameCount <= 1) return;")
    lines.append("")
    lines.append("  unsigned long now = millis();")
    if uniform_timing:
        lines.append("  uint16_t waitMs = frameDelayMs;")
    else:
        lines.append("  uint16_t waitMs = frameDelaysMs[currentFrame];")
    lines.append("")
    lines.append("  if (now - lastFrameTime >= waitMs) {")
    lines.append("    display.clearDisplay();")
    lines.append("    display.drawBitmap(0, 0, getFramePtr(currentFrame), SCREEN_WIDTH, SCREEN_HEIGHT, WHITE);")
    lines.append("    display.display();")
    lines.append("")
    lines.append("    currentFrame = (currentFrame + 1) % frameCount;")
    lines.append("    lastFrameTime = now;")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


