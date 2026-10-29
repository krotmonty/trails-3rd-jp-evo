"""Japanese monster names, descriptions and craft names (ED6_DT30 MS*._DT) for the English game.

Usage: monsters.py EN_DT30_DIR_FILE JP_DT30_DIR EN_DT3C_DIR_FILE JP_MNSNOTE2 OUT_DIR

  EN_DT30_DIR_FILE  the game's ED6_DT30.dir (English monster files are read from it)
  JP_DT30_DIR       the Japanese PC battle files (uncompressed)
  EN_DT3C_DIR_FILE  the game's ED6_DT3C.dir (holds MNSNOTE2, the monster notebook's own copy
                    of every monster)
  JP_MNSNOTE2       the Japanese MNSNOTE2._DT
  OUT_DIR           merged files, uncompressed (SoraVoice loads them loose from voice/scena)

A monster file is battle data with NUL-terminated strings inline (craft names, then the
monster's name and description), read in order by the game. The English and Japanese files hold
nearly the same data and the same strings. Both are cut at every NUL into pieces (data followed
by the text of a string) and the pieces are aligned by their data parts; a merged piece keeps
the English data and takes the Japanese text. Data XSEED changed or added stays English.

A data byte can look like text, so a piece takes the Japanese text only when it really is text:
kana/kanji on the Japanese side, and on the English side two or more characters or an empty
string (then the Japanese needs two or more kana/kanji).
"""

import difflib
import struct
import os
import sys

import ed6arc


def text_start(piece):
    """Where the text at the end of a piece starts: the longest tail that is Shift-JIS text."""
    for i in range(len(piece) + 1):
        try:
            t = piece[i:].decode("cp932")
        except UnicodeDecodeError:
            continue
        if all(ord(c) >= 0x20 for c in t):
            return i
    return len(piece)


def japanese_chars(text):
    """Kana, kanji and full-width characters in Shift-JIS bytes (data rarely decodes to these)."""
    return sum(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF or 0xFF01 <= ord(c) <= 0xFF5E
               for c in text.decode("cp932"))


def merge_piece(e, j):
    e_at, j_at = text_start(e), text_start(j)
    e_len, jp = len(e) - e_at, japanese_chars(j[j_at:])
    # English text (2+ characters) or an empty English string, against real Japanese text
    if e_at == j_at and ((e_len >= 2 and jp >= 1) or (e_len == 0 and jp >= 2)):
        return e[:e_at] + j[j_at:]
    return e


def merge(en, jp):
    """Merged bytes and the number of strings now Japanese."""
    en_p, jp_p = en.split(b"\0"), jp.split(b"\0")

    def keys(pieces):  # data part, plus a mark for pieces that hold a real string
        out = []
        for p in pieces:
            at = text_start(p)
            real = len(p) - at >= 2 or japanese_chars(p[at:]) >= 1
            out.append(p[:at] + b"\0STR" if real else p)
        return out
    out = []
    sm = difflib.SequenceMatcher(None, keys(en_p), keys(jp_p), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            out += [merge_piece(e, j) for e, j in zip(en_p[i1:i2], jp_p[j1:j2])]
            continue
        # Pieces don't line up here (a piece more on one side): pair the pieces that are only
        # text, in order, when both sides have the same number of them.
        block = list(en_p[i1:i2])
        en_t = [k for k, p in enumerate(block) if text_start(p) == 0 and len(p) >= 2]
        jp_t = [p for p in jp_p[j1:j2] if text_start(p) == 0 and japanese_chars(p) >= 1]
        if len(en_t) == len(jp_t):
            for k, j in zip(en_t, jp_t):
                block[k] = j
        out += block
    return b"\0".join(out), sum(a != b for a, b in zip(out, en_p))


def note_records(d):
    """MNSNOTE2: records of u32 monster file ID, u32 size, a copy of the monster data; then 0xFF."""
    recs, pos = [], 0
    while pos + 8 <= len(d):
        fid, size = struct.unpack_from("<II", d, pos)
        if fid >> 16 != 0x30 or pos + 8 + size > len(d):
            break
        recs.append((fid, d[pos + 8:pos + 8 + size]))
        pos += 8 + size
    return recs, d[pos:]


def merge_note(en, jp):
    """The monster notebook keeps its own copy of each monster: merge record by record."""
    en_r, tail = note_records(en)
    jp_r = dict(note_records(jp)[0])
    out, strings = bytearray(), 0
    for fid, data in en_r:
        if fid in jp_r:
            merged, changed = merge(data, jp_r[fid])
            strip = lambda d: [p[:text_start(p)] for p in d.split(b"\0")]
            assert strip(merged) == strip(data), hex(fid)
            data, strings = merged, strings + changed
        out += struct.pack("<II", fid, len(data)) + data
    return bytes(out) + tail, strings


def main():
    en_dir, jp_dir, en_note_dir, jp_note, out_dir = sys.argv[1:6]
    os.makedirs(out_dir, exist_ok=True)
    note, strings = merge_note(ed6arc.decompress(ed6arc.read(en_note_dir, "MNSNOTE2._DT")),
                               open(jp_note, "rb").read())
    open(os.path.join(out_dir, "MNSNOTE2._DT"), "wb").write(note)
    print(f"monster notebook: {strings} strings Japanese")
    ents = ed6arc.entries(en_dir)
    done = strings = 0
    for name in sorted(n for n in os.listdir(jp_dir) if n.startswith("MS")):
        if name not in ents or ents[name][1] == 0:
            continue
        en = ed6arc.decompress(ed6arc.read(en_dir, name))
        jp = open(os.path.join(jp_dir, name), "rb").read()
        data, changed = merge(en, jp)
        # the merged file must be the English file with only the text of its strings changed
        strip = lambda d: [p[:text_start(p)] for p in d.split(b"\0")]
        assert strip(data) == strip(en), name
        if changed:
            open(os.path.join(out_dir, name), "wb").write(data)
            done += 1
            strings += changed
    print(f"{done} monster files, {strings} strings Japanese")


if __name__ == "__main__":
    main()
