from core.vnc_protocol import BPP


def check_rect(fb_w: int, fb_h: int, x: int, y: int, w: int, h: int, error_type):
    if x + w > fb_w or y + h > fb_h:
        raise error_type(
            f"server sent rect {w}x{h}+{x}+{y} outside the "
            f"{fb_w}x{fb_h} framebuffer"
        )


def blit_rect(fb: bytearray, fb_w: int, fb_h: int, x: int, y: int, w: int, h: int, data: bytes, error_type) -> None:
    check_rect(fb_w, fb_h, x, y, w, h, error_type)
    row_bytes = w * BPP
    for row in range(h):
        dst = ((y + row) * fb_w + x) * BPP
        src = row * row_bytes
        fb[dst:dst + row_bytes] = data[src:src + row_bytes]


def copy_rect(
    fb: bytearray,
    fb_w: int,
    fb_h: int,
    src_x: int,
    src_y: int,
    x: int,
    y: int,
    w: int,
    h: int,
    error_type,
) -> None:
    check_rect(fb_w, fb_h, src_x, src_y, w, h, error_type)
    check_rect(fb_w, fb_h, x, y, w, h, error_type)
    row_bytes = w * BPP
    rows = [
        bytes(fb[((src_y + r) * fb_w + src_x) * BPP:
                 ((src_y + r) * fb_w + src_x) * BPP + row_bytes])
        for r in range(h)
    ]
    for r, chunk in enumerate(rows):
        dst = ((y + r) * fb_w + x) * BPP
        fb[dst:dst + row_bytes] = chunk
