import io
import os
import zipfile

import streamlit as st
from PIL import Image

import oled_core


def upload_sort_key(file):
    number = oled_core.find_first_number(file.name)
    if number is None:
        number = 10 ** 18
    return (number, file.name.lower())


st.set_page_config(page_title="Lux Taylor OLED Generator", layout="wide")
st.title("Lux Taylor Art / Arduino Animated OLED Generator")

st.sidebar.header("Settings")

board_name = st.sidebar.selectbox("Board", list(oled_core.BOARDS.keys()), index=0)
protocol = st.sidebar.selectbox("Protocol", oled_core.PROTOCOLS, index=0)
resolution = st.sidebar.selectbox("OLED resolution", oled_core.RESOLUTIONS, index=0)

width_text, height_text = resolution.split("x")
width = int(width_text)
height = int(height_text)

board = oled_core.BOARDS[board_name]

if protocol == "I2C":
    data_pin = board["i2c_sda"]
    clock_pin = board["i2c_scl"]
else:
    data_pin = board["spi_mosi"]
    clock_pin = board["spi_sck"]

st.sidebar.subheader("Locked bus pins (info)")
st.sidebar.text("SDA / MOSI: " + data_pin)
st.sidebar.text("SCL / SCK:  " + clock_pin)
st.sidebar.text("MISO:       " + board["spi_miso"])

st.sidebar.subheader("Pins")

if "last_board" not in st.session_state or st.session_state.last_board != board_name:
    st.session_state.pin_cs = board["default_cs"]
    st.session_state.pin_dc = board["default_dc"]
    st.session_state.pin_rst = board["default_rst"]
    st.session_state.last_board = board_name

if protocol == "SPI":
    pin_cs = st.sidebar.text_input("CS", st.session_state.pin_cs)
    pin_dc = st.sidebar.text_input("DC", st.session_state.pin_dc)
else:
    st.sidebar.text_input("CS", st.session_state.pin_cs, disabled=True)
    st.sidebar.text_input("DC", st.session_state.pin_dc, disabled=True)
    pin_cs = st.session_state.pin_cs
    pin_dc = st.session_state.pin_dc

pin_rst = st.sidebar.text_input("RESET (-1 allowed)", st.session_state.pin_rst)

st.sidebar.subheader("Timing")
uniform_timing = st.sidebar.checkbox("Uniform timing", value=True)
uniform_delay_ms = st.sidebar.number_input("Frame timing (ms)", min_value=0, value=250, step=1)

st.subheader("Frames")
uploads = st.file_uploader(
    "Upload BMP frames (multiple). Tip: name them 1.bmp, 2.bmp, 3.bmp...",
    type=["bmp"],
    accept_multiple_files=True
)

frame_files = []
if uploads:
    for file in uploads:
        frame_files.append(file)
    frame_files.sort(key=upload_sort_key)
frame_count = len(frame_files)

left_column, right_column = st.columns([1, 1])
with left_column:
    st.write(f"Frames loaded: **{frame_count}**")
with right_column:
    if frame_count > 0:
        estimate = oled_core.estimate_bitmap_bytes(frame_count, width, height)
        flash = board["flash_bytes"]
        if estimate / flash > 0.70 and flash <= 64 * 1024:
            st.warning(f"⚠ est bitmap data {estimate // 1024}KB (this board may overflow)")
        else:
            st.info(f"est bitmap data: {estimate // 1024}KB")

per_frame_delays = []
if frame_count > 0 and not uniform_timing:
    st.markdown("### Per-frame timing (ms)")
    columns = st.columns(4)
    for i in range(frame_count):
        name_without_extension = os.path.splitext(frame_files[i].name)[0]
        label = str(i).zfill(2) + " • " + name_without_extension
        with columns[i % 4]:
            per_frame_delays.append(st.number_input(label, min_value=0, value=uniform_delay_ms, step=1))

st.markdown("### Resolution mismatch behavior")
mismatch_mode = st.radio(
    "If some BMPs aren't exactly the selected resolution:",
    ["Stop and show mismatch list", "Auto-crop/pad to selected resolution"],
    index=0
)

uploaded_files_info = []
for file in frame_files:
    uploaded_files_info.append(file.name + " " + str(file.size))

current_inputs = [board_name, protocol, resolution, pin_cs, pin_dc, pin_rst, uniform_timing,
                  uniform_delay_ms, per_frame_delays, mismatch_mode, uploaded_files_info]

st.markdown("---")
generate = st.button("Generate Code", disabled=(frame_count == 0))

if generate:
    images = []
    mismatches = []
    for file in frame_files:
        image = Image.open(io.BytesIO(file.getvalue()))
        if image.width != width or image.height != height:
            mismatches.append(file.name + ": " + str(image.width) + "x" + str(image.height))
        images.append(image)

    if len(mismatches) > 0 and mismatch_mode == "Stop and show mismatch list":
        if "sketch_ino" in st.session_state:
            del st.session_state["sketch_ino"]
        st.error("One or more BMPs don't match the selected resolution.")
        for i in range(len(mismatches)):
            if i < 20:
                st.write("- " + mismatches[i])
        if len(mismatches) > 20:
            st.write(f"...and {len(mismatches) - 20} more")
        st.stop()

    frames = []
    for image in images:
        if image.width != width or image.height != height:
            image = oled_core.center_crop(image, width, height)
        frames.append(oled_core.image_to_bytes(image, width, height))

    file_names = []
    for file in frame_files:
        file_names.append(file.name)

    reset_pin = pin_rst.strip()
    if reset_pin == "":
        reset_pin = "-1"

    st.session_state.bitmaps_h = oled_core.generate_bitmaps_h(file_names, width, height, frames)
    st.session_state.sketch_ino = oled_core.generate_sketch_ino(
        board_name,
        protocol,
        width,
        height,
        pin_cs.strip(),
        pin_dc.strip(),
        reset_pin,
        uniform_timing,
        uniform_delay_ms,
        per_frame_delays,
    )
    st.session_state.generated_inputs = current_inputs

if "sketch_ino" in st.session_state:
    sketch_ino = st.session_state.sketch_ino
    bitmaps_h = st.session_state.bitmaps_h

    if st.session_state.generated_inputs != current_inputs:
        st.info("Settings or frames changed since this code was generated. Click **Generate Code** to refresh it.")

    tabs = st.tabs(["sketch.ino", "bitmaps.h"])
    with tabs[0]:
        st.code(sketch_ino, language="cpp")
    with tabs[1]:
        st.code(bitmaps_h, language="cpp")

    st.markdown("### Downloads")
    column_1, column_2, column_3 = st.columns(3)

    with column_1:
        st.download_button("Download sketch.ino", data=sketch_ino, file_name="sketch.ino", mime="text/plain")
    with column_2:
        st.download_button("Download bitmaps.h", data=bitmaps_h, file_name="bitmaps.h", mime="text/plain")
    with column_3:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("sketch.ino", sketch_ino)
            zip_file.writestr("bitmaps.h", bitmaps_h)
        st.download_button("Download ZIP (both files)", data=zip_buffer.getvalue(),
                           file_name="oled_generator_output.zip", mime="application/zip")
