"""Read files out of ED6 (Trails in the Sky) .dir/.dat archives and undo their compression.

Usage: ed6arc.py ARCHIVE_DIR_FILE NAME OUT     e.g. ed6arc.py ".../ED6_DT22.dir" "T_MAGIC ._DT" out.bin

A compressed file is a run of chunks: u16 chunk size (counting itself), the chunk data, then one
byte that is nonzero when another chunk follows. Chunk data is an LZ stream driven by 16-bit
flag words, read low bit first.
"""

import struct
import sys


def entries(dir_path):
    """{name: (offset, size)} from a .dir file."""
    d = open(dir_path, "rb").read()
    found = {}
    for i in range(struct.unpack_from("<I", d, 8)[0]):
        e = d[16 + 36 * i: 16 + 36 * (i + 1)]
        name = e[:12].decode("ascii", "replace")
        if name.strip("\0 "):
            _, size, _, _, _, off = struct.unpack_from("<6I", e, 12)
            found[name] = (off, size)
    return found


def read(dir_path, name):
    off, size = entries(dir_path)[name]
    with open(dir_path[:-4] + ".dat", "rb") as f:
        f.seek(off)
        return f.read(size)


class _Bits:
    def __init__(self, data, pos):
        self.data, self.pos = data, pos + 2
        self.flags, self.left = data[pos + 1], 8  # the first flag word only uses its high byte

    def byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def bit(self):
        if self.left == 0:
            self.flags = self.data[self.pos] | self.data[self.pos + 1] << 8
            self.pos += 2
            self.left = 16
        b = self.flags & 1
        self.flags >>= 1
        self.left -= 1
        return b

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | self.bit()
        return v

    def count(self):
        for n in (2, 3, 4, 5):
            if self.bit():
                return n
        if self.bit():
            return 6 + self.bits(3)
        return 14 + self.byte()


def _chunk(data, pos, out):
    b = _Bits(data, pos)
    while True:
        if not b.bit():
            out.append(b.byte())
            continue
        if not b.bit():
            off = b.byte()
        else:
            off = b.bits(5) << 8 | b.byte()
            if off == 0:
                return
            if off == 1:
                n = (b.bits(4) << 8 | b.byte()) if b.bit() else b.bits(4)
                out.extend([b.byte()] * (n + 14))
                continue
        for _ in range(b.count()):
            out.append(out[-off])


def decompress(data):
    out = bytearray()
    pos = 0
    while True:
        size = struct.unpack_from("<H", data, pos)[0]
        _chunk(data, pos + 2, out)
        pos += size
        if pos >= len(data) or not data[pos]:
            return bytes(out)
        pos += 1


if __name__ == "__main__":
    dir_path, name, out = sys.argv[1:4]
    with open(out, "wb") as f:
        f.write(decompress(read(dir_path, name)))
