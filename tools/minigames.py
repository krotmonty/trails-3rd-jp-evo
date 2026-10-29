"""Japanese text for the fishing, quiz and poker minigames, keeping the Evo voice cues.

Usage: minigames.py INSTALLED_TXT_DIR EVO_TXT_DIR PC_QUIZ_TXT_DIR POKER_DIR OUT_TXT_DIR

  INSTALLED_TXT_DIR  the voiced English T_FISH.txt / T_QUIZ0n.txt (Fish2Txt / Quiz2Txt of the
                     installed _DT files); they give the voice cues (#NNNNNv) and the layout
  EVO_TXT_DIR        SoraVoiceScripts en.3rd/mg.txt.evo (Japanese Evo text with voice IDs)
  PC_QUIZ_TXT_DIR    Quiz2Txt of the Japanese PC T_QUIZ0n._DT, for questions Evo replaced
  POKER_DIR          the installed Z_POKER8._DT / Z_POKER9._DT (string patch lists)
  OUT_TXT_DIR        Japanese T_FISH.txt / T_QUIZ0n.txt for Txt2Fish / Txt2Quiz, and the
                     Japanese Z_POKER8._DT / Z_POKER9._DT, ready to install

Every Japanese line is checked to belong to the same recording as the English line it replaces
(the English cue maps to the Evo voice ID); a mismatch stops the build.
"""

import os
import re
import sys

import voicemap

EVO_CODES = re.compile(r"#\d+[JVBZLY]|#\d+R[^#]*#")
LEAD = re.compile(r"^((?:#\d+[A-Za-z])*)")
CUE = re.compile(r"^#(\d+)v")
TERM = re.compile(r"((?:\[x0[23]\])+)$")
# Characters the Evo text uses that Shift-JIS (cp932) spells differently
CP932_FIX = str.maketrans({"〜": "～", "−": "－", "‖": "∥"})


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read().splitlines()


def evo_id(text):
    m = re.search(r"#(\d+)V", text)
    return m.group(1).zfill(10) if m else None  # some Evo IDs drop the leading zero


def check_voice(en, jp, where):
    cue = CUE.match(en)
    if not cue:
        return ""
    want = voicemap.full_id(cue.group(1))
    if evo_id(jp) != want:
        raise SystemExit(f"{where}: voice {want} but Evo line has {evo_id(jp)}: {jp[:40]}")
    return cue.group(0)


def jp_body(jp):
    return LEAD.sub("", EVO_CODES.sub("", jp)).translate(CP932_FIX)


def fish(en_lines, evo_lines):
    """English line -> same voice cue and leading codes, Japanese text, same terminator."""
    out = []
    pairs = list(zip(en_lines, evo_lines))
    out.append(en_lines[0])  # file name line
    for n, (en, jp) in enumerate(pairs[1:], 1):
        if not en.strip():
            out.append(en)
            continue
        cue = check_voice(en, jp, f"T_FISH line {n + 1}")
        lead = LEAD.match(en[len(cue):]).group(1)
        tm = TERM.search(en)
        body = TERM.sub("", jp_body(jp))
        out.append(cue + lead + body + (tm.group(1) if tm else ""))
    return out


def quiz(en_lines, evo_lines, pc_lines, name):
    """Blocks of: number, answer, question, 4 choices, comment (voiced).

    Evo text is used where Evo has the same question (found by the comment's voice ID, same
    correct choice). Evo replaced a few questions, reusing their voice slots; those take the
    Japanese PC text, which the English was translated from, so it lines up one to one.
    """
    def blocks(lines):
        return [b.split("\n") for b in "\n".join(lines[1:]).strip("\n").split("\n\n")]
    # The Evo quiz has extra questions, so questions are paired by the comment's voice ID.
    en, pc = blocks(en_lines), blocks(pc_lines)
    if [b[:2] for b in en] != [b[:2] for b in pc]:
        raise SystemExit(f"{name}: English and PC questions don't line up")
    jp = {evo_id(b[7]): b for b in blocks(evo_lines) if len(b) == 8 and evo_id(b[7])}
    out = [en_lines[0]]
    used = {"evo": 0, "pc": 0}
    for e, p in zip(en, pc):
        cue = CUE.match(e[7])
        j = jp.get(voicemap.full_id(cue.group(1))) if cue else None
        src = "evo" if j is not None and j[1] == e[1] else "pc"
        j = j if src == "evo" else p
        used[src] += 1
        out += [""] + e[:2] + [jp_body(x) for x in j[2:7]] + [(cue.group(0) if cue else "") + jp_body(j[7])]
    print(f"{name}: {used['evo']} questions from Evo, {used['pc']} from the PC script")
    return out


def poker(lines):
    """Each English block is followed by the original Japanese block with the same cues: copy it."""
    blocks = "\n".join(lines).split("\n\n")
    parsed = [b.split("\n") for b in blocks]
    changed = 0
    for a, b in zip(parsed, parsed[1:]):
        if len(a) < 3 or len(b) < 3 or len(a) != len(b):
            continue
        cues_a = [CUE.match(x).group(0) if CUE.match(x) else "" for x in a[2:]]
        cues_b = [CUE.match(x).group(0) if CUE.match(x) else "" for x in b[2:]]
        is_jp = any(ord(c) > 0x3000 for c in "".join(b[2:]))
        is_en = not any(ord(c) > 0x3000 for c in "".join(a[2:]))
        if cues_a == cues_b and is_en and is_jp:
            a[2:] = b[2:]
            changed += 1
    return "\n\n".join("\n".join(b) for b in parsed).split("\n"), changed


def main():
    inst, evo, pc, poker_dir, out = sys.argv[1:6]
    os.makedirs(out, exist_ok=True)
    evo_files = {n.lower(): n for n in os.listdir(evo)}

    def write(name, lines):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")

    write("T_FISH.txt", fish(read(os.path.join(inst, "T_FISH.txt")), read(os.path.join(evo, evo_files["t_fish.txt"]))))
    for q in ("01", "02", "03", "04"):
        name = f"T_QUIZ{q}.txt"
        write(name, quiz(read(os.path.join(inst, name)), read(os.path.join(evo, evo_files[name.lower()])),
                         read(os.path.join(pc, name)), name))
    for p in ("Z_POKER8._DT", "Z_POKER9._DT"):
        lines, changed = poker(read(os.path.join(poker_dir, p)))
        write(p, lines)
        print(p, changed, "blocks now Japanese")
    for n in os.listdir(out):
        if n.endswith(".txt"):
            for i, line in enumerate(read(os.path.join(out, n)), 1):
                try:
                    re.sub(r"\[x[0-9A-F]{2}\]", "", line).encode("cp932")
                except UnicodeEncodeError as e:
                    raise SystemExit(f"{n}:{i} not Shift-JIS: {line[max(0, e.start - 3):e.end + 3]!r}")
    print("fish and quiz text written to", out)


if __name__ == "__main__":
    main()
