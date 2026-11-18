import os

from PIL import Image


BOARDS = {
    "Seeeduino XIAO (SAMD21)": {
        "flash_bytes": 256 * 1024,
        "i2c_sda": "D4",
        "i2c_scl": "D5",
        "spi_mosi": "D10",
        "spi_miso": "D9",
        "spi_sck": "D8",
        "default_cs": "D7",
        "default_dc": "D2",
        "default_rst": "D3",
    },
    "Arduino Nano": {
        "flash_bytes": 32 * 1024,
        "i2c_sda": "A4",
        "i2c_scl": "A5",
        "spi_mosi": "D11",
        "spi_miso": "D12",
        "spi_sck": "D13",
        "default_cs": "10",
        "default_dc": "9",
        "default_rst": "8",
    },
    "Seeed XIAO ESP32C6": {
        "flash_bytes": 4 * 1024 * 1024,
        "i2c_sda": "D4",
        "i2c_scl": "D5",
        "spi_mosi": "D10",
        "spi_miso": "D9",
        "spi_sck": "D8",
        "default_cs": "D7",
        "default_dc": "D2",
        "default_rst": "D3",
    },
}

RESOLUTIONS = ["128x64", "128x32"]
PROTOCOLS = ["SPI", "I2C"]

THRESHOLD = 128
BITMAP_DRAW_MODE = "Horizontal 1bpp"

LETTERS_AND_DIGITS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"


def find_first_number(text):
    digits = ""
    for character in text:
        if character.isdecimal():
            digits = digits + character
        elif digits != "":
            break
    if digits == "":
        return None
    return int(digits)


def center_crop(image, target_width, target_height):
    left = max(0, (image.width - target_width) // 2)
    top = max(0, (image.height - target_height) // 2)
    right = left + min(target_width, image.width)
    bottom = top + min(target_height, image.height)
    cropped = image.crop((left, top, right, bottom))

    if cropped.width == target_width and cropped.height == target_height:
        return cropped

    padded = Image.new("L", (target_width, target_height), 0)
    x = (target_width - cropped.width) // 2
    y = (target_height - cropped.height) // 2
    padded.paste(cropped, (x, y))
    return padded


def image_to_bytes(image, width, height):
    gray = image.convert("L")
    pixels = gray.load()
    numbers = []

    for y in range(height):
        byte = 0
        bit_count = 0
        for x in range(width):
            byte = byte * 2
            if pixels[x, y] >= THRESHOLD:
                byte = byte + 1
            bit_count = bit_count + 1
            if bit_count == 8:
                numbers.append(byte)
                byte = 0
                bit_count = 0
        if bit_count != 0:
            while bit_count < 8:
                byte = byte * 2
                bit_count = bit_count + 1
            numbers.append(byte)

    return numbers


def numbers_to_c_array(numbers):
    text = ""
    for i in range(len(numbers)):
        if i > 0:
            if i % 12 == 0:
                text = text + ",\n  "
            else:
                text = text + ", "
        text = text + "0x" + format(numbers[i], "02X")
    return text


def c_name_from_file_name(file_name):
    name = os.path.splitext(os.path.basename(file_name))[0]
    result = ""
    last_was_replaced = False
    for character in name:
        if character in LETTERS_AND_DIGITS:
            result = result + character
            last_was_replaced = False
        elif not last_was_replaced:
            result = result + "_"
            last_was_replaced = True
    if result != "" and result[0] in "0123456789":
        result = "img_" + result
    return result


def estimate_bitmap_bytes(frame_count, width, height):
    per_frame = (width * height) // 8
    pointers = frame_count * 4
    return frame_count * per_frame + pointers


def generate_bitmaps_h(file_names, width, height, frames):
    lines = []
    lines.append("#pragma once")
    lines.append("#include <Arduino.h>")
    lines.append("")
    lines.append("// draw mode: " + BITMAP_DRAW_MODE + ", threshold: " + str(THRESHOLD))
    lines.append("")

    frame_names = []
    for i in range(len(file_names)):
        frame_name = c_name_from_file_name(file_names[i]) + "_" + str(i).zfill(3)
        frame_names.append(frame_name)
        lines.append("const uint8_t " + frame_name + "[] PROGMEM = {")
        lines.append("  " + numbers_to_c_array(frames[i]))
        lines.append("};")
        lines.append("")

    lines.append("const uint8_t* const bmpArray[] PROGMEM = {")
    for frame_name in frame_names:
        lines.append("  " + frame_name + ",")
    lines.append("};")
    lines.append("")
    lines.append("const int frameCount = " + str(len(file_names)) + ";")
    lines.append("const int frameWidth = " + str(width) + ";")
    lines.append("const int frameHeight = " + str(height) + ";")
    return "\n".join(lines)


def generate_sketch_ino(board_name, protocol, width, height, pin_cs, pin_dc, pin_rst,
                        uniform_timing, uniform_delay_ms, per_frame_delays):
    lines = []
    lines.append("// Arduino OLED Animator / Lux Taylor Art")
    lines.append("// board: " + board_name)
    lines.append("// protocol: " + protocol)
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
    lines.append("#define SCREEN_WIDTH " + str(width))
    lines.append("#define SCREEN_HEIGHT " + str(height))
    lines.append("")

    if protocol == "SPI":
        lines.append("#define OLED_CS " + pin_cs)
        lines.append("#define OLED_DC " + pin_dc)
        lines.append("#define OLED_RESET " + pin_rst)
        lines.append("")
        lines.append("Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &SPI, OLED_DC, OLED_RESET, OLED_CS);")
    else:
        lines.append("#define OLED_RESET " + pin_rst)
        lines.append("#define OLED_I2C_ADDR 0x3C")
        lines.append("")
        lines.append("Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);")

    lines.append("")
    lines.append("// timing")
    if uniform_timing:
        delay = uniform_delay_ms
        if delay <= 0:
            delay = 1
        lines.append("const unsigned long frameDelayMs = " + str(delay) + ";")
    else:
        delay_text = ""
        for i in range(len(per_frame_delays)):
            if i > 0:
                delay_text = delay_text + ", "
            delay_text = delay_text + str(per_frame_delays[i])
        lines.append("const unsigned long frameDelaysMs[frameCount] = { " + delay_text + " };")
    lines.append("unsigned long lastFrameTime = 0;")
    lines.append("int currentFrame = 0;")
    lines.append("")

    lines.append("static const uint8_t* getFramePtr(int idx) {")
    lines.append("  return (const uint8_t*)pgm_read_ptr(&bmpArray[idx]);")
    lines.append("}")
    lines.append("")

    lines.append("void setup() {")
    lines.append("  Serial.begin(115200);")
    if protocol == "I2C":
        lines.append("  Wire.begin();")
        lines.append("  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {")
    else:
        lines.append("  if (!display.begin(SSD1306_SWITCHCAPVCC)) {")
    lines.append("    Serial.println(\"OLED not found: check wiring, pins and I2C address\");")
    lines.append("    while (true) {")
    lines.append("      delay(1000);")
    lines.append("    }")
    lines.append("  }")
    lines.append("")
    lines.append("  display.clearDisplay();")
    lines.append("  display.drawBitmap(0, 0, getFramePtr(0), SCREEN_WIDTH, SCREEN_HEIGHT, WHITE);")
    lines.append("  display.display();")
    lines.append("  lastFrameTime = millis();")
    lines.append("}")
    lines.append("")

    lines.append("void loop() {")
    lines.append("  if (frameCount <= 1) return;")
    lines.append("")
    lines.append("  unsigned long now = millis();")
    if uniform_timing:
        lines.append("  unsigned long waitMs = frameDelayMs;")
    else:
        lines.append("  unsigned long waitMs = frameDelaysMs[currentFrame];")
    lines.append("")
    lines.append("  if (now - lastFrameTime >= waitMs) {")
    lines.append("    currentFrame = (currentFrame + 1) % frameCount;")
    lines.append("    display.clearDisplay();")
    lines.append("    display.drawBitmap(0, 0, getFramePtr(currentFrame), SCREEN_WIDTH, SCREEN_HEIGHT, WHITE);")
    lines.append("    display.display();")
    lines.append("    lastFrameTime = now;")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)
