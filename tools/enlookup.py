"""Build voice/web/en.json: Japanese page text -> English page text, for the reading page.

Usage: enlookup.py EN_PY_DIR JP_PY_DIR OUT_JSON

Keys are normalized like the page normalizes what the DLL sends: control codes, ruby,
escapes and all whitespace removed. Pages still in English are left out.
"""

import json
import os
import re
import sys

import jpify

CODE = re.compile(r"#\d+R[^#]*#|#\d+[A-Za-z]")
ESC = re.compile(r"\\x07\\x[0-9A-Fa-f]{2}|\\x[0-9A-Fa-f]{2}")


def unescape(lit):
    return lit.replace('\\"', '"').replace("\\\\", "\\")


def key(lines):
    return re.sub(r"\s", "", unescape(CODE.sub("", ESC.sub("", "".join(lines)))))


def english(lines):
    text = "".join(lines).replace("\\x01", "\n")
    return re.sub(r"[ \t]+\n", "\n", unescape(CODE.sub("", ESC.sub("", text)))).strip()


def main():
    en_dir, jp_dir, out = sys.argv[1:4]
    table = {}
    skipped = 0
    for n in sorted(os.listdir(jp_dir)):
        if not n.endswith(".py"):
            continue
        en = jpify.Script(os.path.join(en_dir, n))
        jp = jpify.Script(os.path.join(jp_dir, n))
        for t in range(len(en.talks)):
            if len(en.talks[t]["pages"]) != len(jp.talks[t]["pages"]):
                skipped += 1
                continue  # a JP page carries its own page break; can't pair pages
            for i in range(len(en.talks[t]["pages"])):
                e, j = en.page_text(t, i), jp.page_text(t, i)
                if e != j:
                    table.setdefault(key(j), english(e))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, separators=(",", ":"))
    print(len(table), "pages,", skipped, "talks skipped")


if __name__ == "__main__":
    main()
