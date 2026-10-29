"""Swap English dialogue in decompiled voiced scena .py files for Japanese text.

Usage: jpify.py EN_DIR OUT_MSG JP_PC_DIR DST_DIR REPORT_JSON

  EN_DIR     decompiled installed (English, voiced) scena .py files: the skeleton
  OUT_MSG    SoraVoiceScripts en.3rd/out.msg (Evo Japanese talk text, cp932)
  JP_PC_DIR  decompiled Japanese PC scena .py files

Japanese sources, per page, in order of preference:
  voice the Evo (Vita) text, matched by voice ID, so it is the line the voice actually says.
        See voice_sources.
  pc    the Japanese PC script. Talks are matched by sequence alignment on (op, speaker, pages)
       within a file group (U7000, U7000_1... share one group), so XSEED's split files work.
Each EN page keeps its voice code (#NNNNv), leading control codes (#F face, #P position...) and
page terminator; only the text in between is replaced. Anything unmatched stays English.
"""

import difflib
import json
import os
import re
import sys
from collections import defaultdict

import voicemap

TALK_OPEN = re.compile(r"^(\s*)(ChrTalk|NpcTalk|AnonymousTalk)\(")
STR_LINE = re.compile(r'^(\s*)"(.*)",\s*$')
HEADER = re.compile(r"^(ChrTalk|NpcTalk|AnonymousTalk) #(\d+)\s*$")

# Codes only the Evo (Vita) engine understands; the PC engine must never see them.
# Evo furigana (#nRruby#) counts n differently from the PC engine, so it is dropped entirely.
EVO_CODES = re.compile(r"#\d+R[^#]*#|#\d+[JVBZLY]")
LEAD_CODES = re.compile(r"^((?:#\d+[A-Za-z])*)")
VOICE = re.compile(r"^#\d+v")
VOICE_ANY = re.compile(r"#\d+v")
TERMINATOR = re.compile(r"(?<!\\x07)((?:\\x02|\\x03)+(?:\\x01)?)$")
COLOR = re.compile(r"\\x07\\x[0-9A-Fa-f]{2}")  # \x07 takes a color byte, which may be \x02
BRACKET_ESC = re.compile(r"\[x([0-9A-Fa-f]{2})\]")


def read_lines(path, enc="utf-8-sig"):
    with open(path, "rb") as f:
        return f.read().decode(enc, "replace").replace("\r\n", "\n").split("\n")


def read_talk_txt(path):
    """Parse an out.py / out.msg file into {index: (op, name, body_lines)}."""
    lines = read_lines(path, "cp932")
    talks = {}
    i = 0
    while i < len(lines):
        m = HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        op, idx = m.group(1), int(m.group(2))
        i += 1
        head = []
        # target line (0x..), then the name line for NpcTalk
        while i < len(lines) and lines[i].strip() and len(head) < (2 if op == "NpcTalk" else 1):
            head.append(lines[i])
            i += 1
        name = head[1] if op == "NpcTalk" and len(head) > 1 else None
        body = []
        while i < len(lines) and not lines[i].startswith(";---"):
            body.append(lines[i])
            i += 1
        talks[idx] = (op, name, body)
    return talks


def pages_by_start(body):
    """{start_line_index: [lines]} for runs of non-blank lines."""
    pages = {}
    cur = None
    for k, line in enumerate(body):
        if line.strip():
            if cur is None:
                cur = k
                pages[cur] = []
            pages[cur].append(line)
        else:
            cur = None
    return pages


def py_escape_jp(text):
    """out.msg text -> body of a Python string literal."""
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return BRACKET_ESC.sub(lambda m: "\\x" + m.group(1).upper(), text)


def find_talks(lines):
    """Locate talk calls in a decompiled .py: list of (op, first_line, last_line)."""
    talks = []
    i = 0
    while i < len(lines):
        m = TALK_OPEN.match(lines[i])
        if m:
            indent = m.group(1)
            j = i + 1
            while j < len(lines) and lines[j].rstrip() != indent + ")":
                j += 1
            talks.append((m.group(2), i, j))
            i = j
        i += 1
    return talks


def py_pages(lines, first, last, op):
    """String-literal lines of one talk: (name_line_idx|None, [[line_idx...] per page])."""
    str_idx = [k for k in range(first + 1, last) if STR_LINE.match(lines[k])]
    name_idx = None
    if op == "NpcTalk" and str_idx:
        name_idx, str_idx = str_idx[0], str_idx[1:]
    pages, cur = [], []
    for k in str_idx:
        cur.append(k)
        if "\\x02" in COLOR.sub("", STR_LINE.match(lines[k]).group(2)):
            pages.append(cur)
            cur = []
    if cur:
        pages.append(cur)
    return name_idx, pages


def lit(lines, k):
    return STR_LINE.match(lines[k]).group(2)


class Script:
    """One decompiled .py with its talks pre-split into pages."""

    def __init__(self, path):
        self.name = os.path.basename(path)[:-3]
        self.lines = read_lines(path)
        self.talks = []
        for op, first, last in find_talks(self.lines):
            name_idx, pages = py_pages(self.lines, first, last, op)
            target = self.lines[first + 1].strip().rstrip(",") if first + 1 < last else ""
            if target.startswith(('"', "(")):  # AnonymousTalk has no speaker argument
                target = ""
            self.talks.append({"op": op, "first": first, "target": target, "name_idx": name_idx, "pages": pages})

    def page_text(self, n, i):
        return [lit(self.lines, k) for k in self.talks[n]["pages"][i]]



def group_of(name):
    return name.split("_")[0].upper()


def voice_sources(scripts, outmsg):
    """{(file, n): ({page i: literal lines}, name)} from out.msg, matched by voice ID.

    Every voiced Evo page carries its full voice ID (#0450630144V); every voiced EN page carries
    the SoraVoice cue for the same recording. A voiced page takes the Evo page with its voice.
    When all voiced pages of a talk come from one Evo talk at the same page numbers and the page
    counts agree, the talk's unvoiced pages are taken from that Evo talk too.
    """
    evo = {}  # voice id -> (talk key, page i, lines)
    talks = {}  # talk key -> (pages, name)
    for fn in sorted(os.listdir(outmsg)):
        for n, (op, name, body) in read_talk_txt(os.path.join(outmsg, fn)).items():
            by_start = pages_by_start(body)
            pages = [by_start[s] for s in sorted(by_start)]
            key = (fn, n)
            talks[key] = (pages, py_escape_jp(name) if op == "NpcTalk" and name else None)
            for i, pg in enumerate(pages):
                ids = voicemap.evo_ids("".join(pg))
                if ids:
                    evo.setdefault(ids[0], (key, i))
    conv = lambda pg: [py_escape_jp(EVO_CODES.sub("", l)) for l in pg]
    found = {}
    for sc in scripts:
        for n, t in enumerate(sc.talks):
            hits = {}
            for i in range(len(t["pages"])):
                ids = voicemap.short_ids("".join(sc.page_text(n, i)))
                if ids and ids[0] in evo:
                    hits[i] = evo[ids[0]]
            if not hits:
                continue
            keys = {k for k, _ in hits.values()}
            name = talks[next(iter(keys))][1] if len(keys) == 1 else None
            if (len(keys) == 1 and all(i == j for i, (_, j) in hits.items())
                    and len(talks[next(iter(keys))][0]) == len(t["pages"])):
                pages = {i: conv(pg) for i, pg in enumerate(talks[next(iter(keys))][0])}
            else:
                pages = {i: conv(talks[k][0][j]) for i, (k, j) in hits.items()}
            found[(sc.name, n)] = (pages, name)
    return found


def signature(t):
    return (t["op"], t["target"], len(t["pages"]))


def pc_sources(scripts, jp_scripts):
    """{(file, n): ({page i: literal lines}, name)} from the Japanese PC scripts."""
    found = {}
    en_groups, jp_groups = defaultdict(list), defaultdict(list)
    for sc in scripts:
        en_groups[group_of(sc.name)].append(sc)
    for sc in jp_scripts:
        jp_groups[group_of(sc.name)].append(sc)
    for grp, ens in en_groups.items():
        jps = jp_groups.get(grp)
        if not jps:
            continue
        a = [(sc, n) for sc in sorted(ens, key=lambda s: s.name) for n in range(len(sc.talks))]
        b = [(sc, n) for sc in sorted(jps, key=lambda s: s.name) for n in range(len(sc.talks))]
        sa = [signature(sc.talks[n]) for sc, n in a]
        sb = [signature(sc.talks[n]) for sc, n in b]
        sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for (esc, en), (jsc, jn) in zip(a[i1:i2], b[j1:j2]):
                jt = jsc.talks[jn]
                pages = {i: jsc.page_text(jn, i) for i in range(len(jt["pages"]))}
                name = lit(jsc.lines, jt["name_idx"]) if jt["name_idx"] is not None else None
                found[(esc.name, en)] = (pages, name)
    return found


UI_COMMANDS = {"Menu", "SetChrName", "OP_CC", "BuildStringList"}  # on-screen text outside talks
COMMAND = re.compile(r"^\s+([A-Za-z_0-9]+)\(")
LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')


def code_tokens(sc):
    """(token, line index | None) per line, string contents blanked and each talk as one token."""
    in_talk = {}
    for op, first, last in find_talks(sc.lines):
        in_talk[first] = last
    out = []
    k = 0
    while k < len(sc.lines):
        if k in in_talk:
            out.append(("TALK", None))
            k = in_talk[k] + 1
            continue
        out.append((re.sub(r"\s+", " ", LITERAL.sub('""', sc.lines[k])).strip(), k))
        k += 1
    return out


def ui_strings(scripts, jp_scripts):
    """Put Japanese into choice menus, speaker names and labels (UI_COMMANDS), in place.

    The English and Japanese PC scripts are the same code with different text, so their lines
    are aligned with string contents blanked; where the code matches exactly, the Japanese
    strings are copied into the English line. Returns the number of lines changed per command.
    """
    count = defaultdict(int)
    en_groups, jp_groups = defaultdict(list), defaultdict(list)
    for sc in scripts:
        en_groups[group_of(sc.name)].append(sc)
    for sc in jp_scripts:
        jp_groups[group_of(sc.name)].append(sc)
    for grp, ens in en_groups.items():
        jps = jp_groups.get(grp)
        if not jps:
            continue
        a = [(sc, tok, k) for sc in sorted(ens, key=lambda s: s.name) for tok, k in code_tokens(sc)]
        b = [(sc, tok, k) for sc in sorted(jps, key=lambda s: s.name) for tok, k in code_tokens(sc)]
        sm = difflib.SequenceMatcher(None, [t for _, t, _ in a], [t for _, t, _ in b], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for (esc, _, ek), (jsc, _, jk) in zip(a[i1:i2], b[j1:j2]):
                if ek is None:
                    continue
                cmd = None
                for k in range(ek, -1, -1):  # the command this line belongs to
                    m = COMMAND.match(esc.lines[k])
                    if m:
                        cmd = m.group(1)
                        break
                jp_lits = LITERAL.findall(jsc.lines[jk])
                if cmd not in UI_COMMANDS or not any(ord(c) > 0x7F for c in "".join(jp_lits)):
                    continue
                it = iter(jp_lits)
                esc.lines[ek] = LITERAL.sub(lambda m: next(it), esc.lines[ek])
                count[cmd] += 1
    return dict(count)


def convert(sc, sources):
    """sources: [(label, {(file, n): ({page i: lines}, name)})] in order of preference."""
    lines = sc.lines
    replace = {}  # line index -> new list of lines (empty list deletes)
    st = {"talks": len(sc.talks), "pages": 0, "en_kept": 0, **{label: 0 for label, _ in sources}}
    for n, t in enumerate(sc.talks):
        st["pages"] += len(t["pages"])
        got = [(label, *src.get((sc.name, n), ({}, None))) for label, src in sources]
        name = next((nm for _, _, nm in got if nm), None)
        if t["name_idx"] is not None and name:
            ind = STR_LINE.match(lines[t["name_idx"]]).group(1)
            replace[t["name_idx"]] = [f'{ind}"{name}",']
        for i, pidx in enumerate(t["pages"]):
            en_page = "".join(lit(lines, k) for k in pidx)
            if len(VOICE_ANY.findall(en_page)) > (1 if VOICE.match(en_page) else 0):
                st["en_kept"] += 1  # voice cue in mid-page: keep English so no voice is lost
                continue
            hit = next(((label, pages[i]) for label, pages, _ in got if i in pages), None)
            if hit:
                src, body = hit[0], list(hit[1])
            else:
                st["en_kept"] += 1
                continue
            first_body, last_body = lit(lines, pidx[0]), lit(lines, pidx[-1])
            ind = STR_LINE.match(lines[pidx[0]]).group(1)
            vm = VOICE.match(first_body)
            voice = vm.group(0) if vm else ""
            lead = LEAD_CODES.match(first_body[len(voice):]).group(1)
            tm = TERMINATOR.search(last_body)
            term = tm.group(1) if tm else ""

            body[0] = LEAD_CODES.sub("", body[0], count=1)
            body[-1] = TERMINATOR.sub("", body[-1]) + term
            body[0] = voice + lead + body[0]

            replace[pidx[0]] = [f'{ind}"{b}",' for b in body]
            for k in pidx[1:]:
                replace[k] = []
            st[src] += 1
        # A single text string is passed bare; several must sit in a tuple, so wrap when JP adds lines
        if t["pages"]:
            a, b = t["pages"][0][0], t["pages"][-1][-1]
            ind = STR_LINE.match(lines[a]).group(1)
            call_ind = TALK_OPEN.match(lines[t["first"]]).group(1)
            if a == b and ind == call_ind + "    ":  # one bare string argument
                if len(replace.get(a, [lines[a]])) > 1:
                    for k in range(a, b + 1):
                        replace[k] = ["    " + l for l in replace.get(k, [lines[k]])]
                    replace[a] = [f"{ind}("] + replace[a]
                    replace[b] = replace[b] + [f"{ind})"]
    out = []
    for k, line in enumerate(lines):
        out.extend(replace.get(k, [line]))
    return out, st


def main():
    en_dir, outmsg, jp_pc_dir, dst_dir, report = sys.argv[1:6]
    os.makedirs(dst_dir, exist_ok=True)
    scripts = [Script(os.path.join(en_dir, n)) for n in sorted(os.listdir(en_dir)) if n.endswith(".py")]
    jp_scripts = [Script(os.path.join(jp_pc_dir, n)) for n in sorted(os.listdir(jp_pc_dir)) if n.endswith(".py")]
    sources = [("voice", voice_sources(scripts, outmsg)), ("pc", pc_sources(scripts, jp_scripts))]
    print("choices, names and labels:", ui_strings(scripts, jp_scripts))
    stats = {}
    for sc in scripts:
        out, stats[sc.name] = convert(sc, sources)
        with open(os.path.join(dst_dir, sc.name + ".py"), "w", encoding="utf-8-sig", newline="") as f:
            f.write("\n".join(out))
    with open(report, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1, ensure_ascii=False)
    tot = {k: sum(s[k] for s in stats.values()) for k in ("pages", "voice", "pc", "en_kept")}
    print("files:", len(stats), tot)
    worst = sorted(((s["en_kept"], k) for k, s in stats.items() if s["en_kept"]), reverse=True)[:15]
    print("most English left:", worst)


if __name__ == "__main__":
    main()
