# streamlit_app.py
import io
import os
import zipfile
import streamlit as st
from PIL import Image

from oled_core import (
    BOARDS, PROTOCOLS, RESOLUTIONS,
    find_first_int, center_crop,
    image_to_1bpp_horizontal_bytes,
    estimate_bitmap_bytes,
    generate_bitmaps_h, generate_sketch_ino,
    THRESHOLD
)

st.set_page_config(page_title="Lux Taylor OLED Generator", layout="wide")
st.title("Lux Taylor Art / Arduino Animated OLED Generator")

# ----------------------------
# Sidebar: Settings
# ----------------------------
st.sidebar.header("Settings")

board_name = st.sidebar.selectbox("Board", list(BOARDS.keys()), index=0)
protocol = st.sidebar.selectbox("Protocol", PROTOCOLS, index=0)
res = st.sidebar.selectbox("OLED resolution", RESOLUTIONS, index=0)

w_str, h_str = res.split("x")
W, H = int(w_str), int(h_str)

b = BOARDS[board_name]


if protocol == "I2C":
    locked_sda_mosi = b.i2c_sda
    locked_scl_sck = b.i2c_scl
else:
    locked_sda_mosi = b.spi_mosi
    locked_scl_sck = b.spi_sck

st.sidebar.subheader("Locked bus pins (info)")
st.sidebar.text(f"SDA / MOSI: {locked_sda_mosi}")
st.sidebar.text(f"SCL / SCK:  {locked_scl_sck}")
st.sidebar.text(f"MISO:       {b.spi_miso}")

st.sidebar.subheader("Pins")

if "pin_cs" not in st.session_state:
    st.session_state.pin_cs = b.default_cs
    st.session_state.pin_dc = b.default_dc
    st.session_state.pin_rst = b.default_rst


if "last_board" not in st.session_state:
    st.session_state.last_board = board_name
if st.session_state.last_board != board_name:
    st.session_state.pin_cs = b.default_cs
    st.session_state.pin_dc = b.default_dc
    st.session_state.pin_rst = b.default_rst
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

def sort_uploads(files):

    scored = []
    for f in files:
        n = find_first_int(f.name)
        scored.append((n if n is not None else 10**18, f.name.lower(), f))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored]

frame_files = sort_uploads(uploads) if uploads else []
frame_count = len(frame_files)

colA, colB = st.columns([1, 1])
with colA:
    st.write(f"Frames loaded: **{frame_count}**")
with colB:
    if frame_count:
        est = estimate_bitmap_bytes(frame_count, W, H)
        ratio = est / max(1, b.flash_bytes)
        if ratio > 0.70 and b.flash_bytes <= 64 * 1024:
            st.warning(f"⚠ est bitmap data {est//1024}KB (this board may overflow)")
        else:
            st.info(f"est bitmap data: {est//1024}KB")


per_frame_delays = []
if frame_count and not uniform_timing:
    st.markdown("### Per-frame timing (ms)")
    default_ms = int(uniform_delay_ms)

    cols = st.columns(4)
    for i, f in enumerate(frame_files):
        with cols[i % 4]:
            per_frame_delays.append(
                st.number_input(f"{i:02d} • {os.path.splitext(f.name)[0]}", min_value=0, value=default_ms, step=1)
            )


st.markdown("### Resolution mismatch behavior")
mismatch_mode = st.radio(
    "If some BMPs aren't exactly the selected resolution:",
    ["Stop and show mismatch list", "Auto-crop/pad to selected resolution"],
    index=0
)


st.markdown("---")
generate = st.button("Generate Code", disabled=(frame_count == 0))

if generate:

    loaded_imgs = []
    mismatches = []

    for f in frame_files:
        im = Image.open(io.BytesIO(f.read()))
        if im.size != (W, H):
            mismatches.append((f.name, im.size))
        loaded_imgs.append(im)

    if mismatches and mismatch_mode == "Stop and show mismatch list":
        st.error("One or more BMPs don't match the selected resolution.")
        for name, sz in mismatches[:20]:
            st.write(f"- {name}: {sz[0]}x{sz[1]}")
        if len(mismatches) > 20:
            st.write(f"...and {len(mismatches)-20} more")
        st.stop()


    if mismatches and mismatch_mode == "Auto-crop/pad to selected resolution":
        loaded_imgs = [center_crop(im, W, H) for im in loaded_imgs]


    frame_bytes = []
    for im in loaded_imgs:
        if im.size != (W, H):
            im = center_crop(im, W, H)
        frame_bytes.append(image_to_1bpp_horizontal_bytes(im, W, H, THRESHOLD))


    if uniform_timing:
        delays = [int(uniform_delay_ms)] * frame_count
    else:
        delays = [int(x) for x in per_frame_delays]
        if len(delays) != frame_count:
            delays = [int(uniform_delay_ms)] * frame_count


    fake_paths = [f.name for f in frame_files]
    bitmaps_h = generate_bitmaps_h(fake_paths, W, H, frame_bytes)

    sketch_ino = generate_sketch_ino(
        board_name=board_name,
        protocol=protocol,
        w=W,
        h=H,
        pin_cs=str(pin_cs).strip(),
        pin_dc=str(pin_dc).strip(),
        pin_rst=str(pin_rst).strip() or "-1",
        uniform_timing=uniform_timing,
        uniform_delay_ms=int(uniform_delay_ms),
        per_frame_delays=delays
    )


    tab1, tab2 = st.tabs(["sketch.ino", "bitmaps.h"])
    with tab1:
        st.code(sketch_ino, language="cpp")
    with tab2:
        st.code(bitmaps_h, language="cpp")


    st.markdown("### Downloads")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.download_button(
            "Download sketch.ino",
            data=sketch_ino.encode("utf-8"),
            file_name="sketch.ino",
            mime="text/plain"
        )
    with c2:
        st.download_button(
            "Download bitmaps.h",
            data=bitmaps_h.encode("utf-8"),
            file_name="bitmaps.h",
            mime="text/plain"
        )
    with c3:

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("sketch.ino", sketch_ino)
            z.writestr("bitmaps.h", bitmaps_h)
        zip_buf.seek(0)

        st.download_button(
            "Download ZIP (both files)",
            data=zip_buf,
            file_name="oled_generator_output.zip",
            mime="application/zip"
        )

