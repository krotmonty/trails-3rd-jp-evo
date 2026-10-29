"""Check Japanese scena builds before they go into the game.

Usage: check.py EN_PY_DIR JP_PY_DIR JP_SN_DIR JP_PC_PY_DIR OUT_MSG REPORT_JSON

A file passes when:
  - it compiled (JP_SN_DIR has it) and every string encodes as ms932,
  - outside talk text, its .py is identical to the English voiced .py (same commands; only
    the text of strings may turn Japanese: choices, speaker names, labels),
  - it has exactly the same voice codes (#NNNNv) as the English voiced file, in the same order,
  - no Evo-only control codes (#..J/V/B/Z/L/R/Y) are left,
  - no text line is wider than the widest line in the Japanese PC script,
  - every voiced page that was changed shows the Evo text recorded for its voice (out.msg).
Prints failing files; the report lists every problem.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jpify  # noqa: E402
import voicemap  # noqa: E402

VOICE_ANY = re.compile(r"#(\d+)v")
EVO_LEFT = re.compile(r"#\d+[JVBZLY]")  # R is furigana, which the PC engine has too
CODES = re.compile(r"#\d+[A-Za-z]|\\x[0-9A-Fa-f]{2}")


def text_lines(sc):
    """Line indices of talk text (and NpcTalk names) in a Script."""
    idx = set()
    for t in sc.talks:
        if t["name_idx"] is not None:
            idx.add(t["name_idx"])
        for p in t["pages"]:
            idx.update(p)
    return idx


def same_command(en_line, jp_line):
    """Identical, or only the text of strings changed to Japanese (choices, names, labels)."""
    if en_line == jp_line:
        return True
    blank = lambda l: re.sub(r"\s+", " ", jpify.LITERAL.sub('""', l)).strip()
    jp_lits = jpify.LITERAL.findall(jp_line)
    return blank(en_line) == blank(jp_line) and any(ord(c) > 0x7F for c in "".join(jp_lits))


def plain(text):
    """Text without control codes, escapes or whitespace, for comparing lines."""
    text = jpify.BRACKET_ESC.sub("", jpify.EVO_CODES.sub("", text))
    text = CODES.sub("", text).replace('\\"', '"').replace("\\\\", "\\")
    return re.sub(r"\s", "", text)


def evo_by_voice(outmsg):
    """Full voice ID -> plain text of the Evo page that carries it."""
    found = {}
    for fn in os.listdir(outmsg):
        for _, _, body in jpify.read_talk_txt(os.path.join(outmsg, fn)).values():
            for pg in jpify.pages_by_start(body).values():
                ids = voicemap.evo_ids("".join(pg))
                if ids:
                    found.setdefault(ids[0], plain("".join(pg)))
    return found


def width(literal):
    """Display width of one text line in half-width units."""
    s = CODES.sub("", literal).replace('\\"', '"').replace("\\\\", "\\")
    return sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in s)


def main():
    en_dir, jp_dir, sn_dir, pc_dir, outmsg, report = sys.argv[1:7]
    evo = evo_by_voice(outmsg)
    sn = {n.split(".")[0].strip().upper() for n in os.listdir(sn_dir)}

    max_w = 0
    for n in os.listdir(pc_dir):
        if n.endswith(".py"):
            sc = jpify.Script(os.path.join(pc_dir, n))
            for k in text_lines(sc):
                max_w = max(max_w, width(jpify.lit(sc.lines, k)))

    problems = {}
    for n in sorted(os.listdir(jp_dir)):
        if not n.endswith(".py"):
            continue
        name = n[:-3]
        en = jpify.Script(os.path.join(en_dir, n))
        jp = jpify.Script(os.path.join(jp_dir, n))
        p = []
        if name.upper() not in sn:
            p.append("did not compile")

        en_rest = [l for k, l in enumerate(en.lines) if k not in text_lines(en) and l.strip() not in "()"]
        jp_rest = [l for k, l in enumerate(jp.lines) if k not in text_lines(jp) and l.strip() not in "()"]
        if len(en_rest) != len(jp_rest) or any(not same_command(e, j) for e, j in zip(en_rest, jp_rest)):
            p.append("commands differ from English")
        if [t["op"] for t in en.talks] != [t["op"] for t in jp.talks]:
            p.append("talk list differs from English")

        jp_text = [jpify.lit(jp.lines, k) for k in sorted(text_lines(jp))]
        en_text = [jpify.lit(en.lines, k) for k in sorted(text_lines(en))]
        if VOICE_ANY.findall("".join(en_text)) != VOICE_ANY.findall("".join(jp_text)):
            p.append("voice codes differ")
        wrong = 0
        for t_en, t_jp in zip(en.talks, jp.talks):
            for p_en, p_jp in zip(t_en["pages"], t_jp["pages"]):
                e = "".join(jpify.lit(en.lines, k) for k in p_en)
                j = "".join(jpify.lit(jp.lines, k) for k in p_jp)
                ids = voicemap.short_ids(e)
                if e != j and ids and ids[0] in evo and plain(j) != evo[ids[0]]:
                    wrong += 1
        if wrong:
            p.append(f"{wrong} voiced pages show a different line than their voice")
        if any(EVO_LEFT.search(l) for l in jp_text):
            p.append("Evo control codes left")
        for l in jp_text:
            try:
                l.encode("ms932")
            except UnicodeEncodeError as e:
                p.append(f"not ms932: {l[max(0, e.start - 5):e.end + 5]!r}")
                break
        wide = [l for l in jp_text if width(l) > max_w and any(ord(c) > 0x7F for c in l)]
        if wide:
            p.append(f"{len(wide)} lines wider than {max_w}: {wide[0][:60]!r}")
        if p:
            problems[name] = p

    with open(report, "w", encoding="utf-8") as f:
        json.dump({"max_width": max_w, "problems": problems}, f, indent=1, ensure_ascii=False)
    print(f"max line width {max_w}; {len(problems)} files with problems")
    for name, p in problems.items():
        print(" ", name, "|", "; ".join(p)[:200])


if __name__ == "__main__":
    main()
