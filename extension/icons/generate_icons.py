"""
Generate GOOPHER extension PNG icons with the Python standard library only
(no Pillow needed). Produces solid brand-red rounded squares at 16/48/128 px.

Run:  python extension/icons/generate_icons.py
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = (200, 16, 46)      # JCPenney-ish red
BG = (255, 255, 255, 0)    # transparent


def _png(width: int, height: int, pixels: bytes) -> bytes:
    """Encode RGBA pixel bytes into a minimal PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    # Add the mandatory filter byte (0) at the start of each scanline.
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def make_icon(size: int) -> bytes:
    r = max(2, size // 6)  # corner radius for a rounded square
    px = bytearray()
    for y in range(size):
        for x in range(size):
            # Rounded-corner mask.
            inside = True
            for (cx, cy) in ((r, r), (size - r, r), (r, size - r), (size - r, size - r)):
                if (x < r or x > size - r) and (y < r or y > size - r):
                    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                        inside = False
            if inside:
                px.extend(bytes(BRAND) + b"\xff")
            else:
                px.extend(bytes((BG[0], BG[1], BG[2], BG[3])))
    return _png(size, size, bytes(px))


def main() -> None:
    for size in (16, 48, 128):
        out = HERE / f"icon{size}.png"
        out.write_bytes(make_icon(size))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
