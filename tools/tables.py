"""Build Japanese menu/name tables (ED6_DT22 T_*._DT) for the English game, and the JP/EN switch.

Usage: tables.py EN_DT22_DIR_FILE JP_DT22_DIR OUT_DIR SWITCH_BAT

  EN_DT22_DIR_FILE  the game's ED6_DT22.dir (English tables are read and decompressed from it)
  JP_DT22_DIR       the Japanese PC tables (uncompressed)
  OUT_DIR           Japanese tables, uncompressed (SoraVoice loads them loose from voice/scena)
  SWITCH_BAT        the "Menu text JP-EN.bat" to write: moves the tables between voice/scena
                    (Japanese) and voice/jp-options (English, the game's own tables)

Merged tables share one layout: a u16 offset per record; a record is H bytes of data, K u16
offsets to NUL-terminated strings, then the strings. They keep the English data (XSEED
rebalanced crafts, added an item and a quest) and take the strings from the Japanese record with
the same ID (first u16 of the record), or the same index for tables without IDs. Records that
exist only in English stay English. Whole tables have their own layouts and are pure text; the
Japanese file is used when it has as many entries as the English one.
"""

import os
import struct
import sys

import ed6arc

MERGED = {  # name: (data bytes H, records keyed by their first u16)
    "T_MAGIC ._DT": (28, False),  # arts and crafts
    "T_ITTXT ._DT": (4, True),    # item names and descriptions
    "T_ITTXT2._DT": (4, True),    # equipment names and descriptions
    "T_MEMO  ._DT": (4, True),    # notebook headings
    "T_QUEST ._DT": (18, True),   # bracer quests
    "T_COOK2 ._DT": (42, True),   # recipes
    "T_TITLE ._DT": (0, False),   # chapter titles
}
WHOLE = ["T_NAME  ._DT", "T_SHOP  ._DT", "T_TOWN  ._DT", "T_CHAIN ._DT"] + [f"T_BOOK{i:02d}._DT" for i in range(1, 17)]


def offsets(d):
    n = struct.unpack_from("<H", d)[0] // 2
    return list(struct.unpack_from(f"<{n}H", d))


def records(d, H):
    out = []
    for a in offsets(d):
        k = (struct.unpack_from("<H", d, a + H)[0] - (a + H)) // 2
        ptrs = struct.unpack_from(f"<{k}H", d, a + H)
        out.append((d[a:a + H], [d[p:d.index(b"\0", p)] for p in ptrs]))
    return out


def build(recs):
    body = bytearray()
    offs = []
    base = 2 * len(recs)
    for head, strs in recs:
        a = base + len(body)
        offs.append(a)
        p, ptrs = a + len(head) + 2 * len(strs), []
        for s in strs:
            ptrs.append(p)
            p += len(s) + 1
        body += head + struct.pack(f"<{len(ptrs)}H", *ptrs) + b"".join(s + b"\0" for s in strs)
    if base + len(body) > 0xFFFF:
        raise ValueError("table too large for 16-bit offsets")
    return struct.pack(f"<{len(offs)}H", *offs) + bytes(body)


def merge(en, jp, H, keyed):
    en_r, jp_r = records(en, H), records(jp, H)
    key = (lambda i, r: struct.unpack_from("<H", r[0])[0]) if keyed else (lambda i, r: i)
    jp_by = {key(i, r): r for i, r in enumerate(jp_r)}
    out, kept = [], 0
    for i, (head, strs) in enumerate(en_r):
        j = jp_by.get(key(i, (head, strs)))
        if j is not None and len(j[1]) == len(strs):
            out.append((head, j[1]))
        else:
            out.append((head, strs))
            kept += 1
    merged = build(out)
    assert records(merged, H) == out
    return merged, len(en_r), kept


def main():
    en_dir, jp_dir, out_dir, bat = sys.argv[1:5]
    os.makedirs(out_dir, exist_ok=True)
    built = []
    for name, (H, keyed) in MERGED.items():
        en = ed6arc.decompress(ed6arc.read(en_dir, name))
        jp = open(os.path.join(jp_dir, name), "rb").read()
        data, n, kept = merge(en, jp, H, keyed)
        open(os.path.join(out_dir, name), "wb").write(data)
        built.append(name)
        print(f"{name}  merged: {n} records, {kept} kept English")
    for name in WHOLE:
        en = ed6arc.decompress(ed6arc.read(en_dir, name))
        jp = open(os.path.join(jp_dir, name), "rb").read()
        if len(offsets(en)) != len(offsets(jp)):
            print(f"{name}  SKIPPED: {len(offsets(en))} English entries, {len(offsets(jp))} Japanese")
            continue
        open(os.path.join(out_dir, name), "wb").write(jp)
        built.append(name)
        print(f"{name}  whole Japanese file ({len(offsets(jp))} entries)")
    files = " ".join(f'"{n}"' for n in built + ["MNSNOTE2._DT"])  # notebook, from monsters.py
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(f"""@echo off
rem Switch menus, names, items, skills, quests, books, recipes and monsters between Japanese and English.
rem Japanese: the tables sit in voice\\scena, where SoraVoice loads them instead of the game's.
rem English:  they wait in voice\\jp-options and the game uses its own English tables.
cd /d "%~dp0voice"
if not exist jp-options mkdir jp-options
if exist "scena\\T_MAGIC ._DT" (
    for %%f in ({files}) do if exist "scena\\%%~f" move /y "scena\\%%~f" "jp-options\\%%~f" >nul
    if exist "scena\\MS*._DT" move /y "scena\\MS*._DT" "jp-options\\" >nul
    echo Menu text is now ENGLISH.
) else (
    for %%f in ({files}) do if exist "jp-options\\%%~f" move /y "jp-options\\%%~f" "scena\\%%~f" >nul
    if exist "jp-options\\MS*._DT" move /y "jp-options\\MS*._DT" "scena\\" >nul
    echo Menu text is now JAPANESE.
)
echo If the game is running, restart it to see the change.
pause
""")
    print(f"{len(built)} tables, switch written to {bat}")


if __name__ == "__main__":
    main()
