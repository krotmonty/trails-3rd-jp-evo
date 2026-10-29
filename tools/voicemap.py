"""Voice IDs: SoraVoice short cues (#95517v) and Evo text codes (#0450630144V) to full voice IDs.

A short cue of n digits indexes SoraVoice's kVoiceIdMapping table after adding
kVoiceIdAdjustAdder[n] (same rule as sora_voice.cpp); longer cues are already full IDs.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPING_H = os.path.join(HERE, "..", "src", "SoraVoice", "src", "ed_voice", "core", "voice_id_mapping.h")
ADDER = [111110, 111100, 111000, 110000, 100000, 0]

SHORT = re.compile(r"#(\d+)v")
EVO = re.compile(r"#(\d+)V")

_table = None


def table():
    global _table
    if _table is None:
        with open(MAPPING_H, encoding="ascii") as f:
            body = f.read().split("kVoiceIdMapping", 1)[1]
        _table = re.findall(r'"(\d*)"', body)
    return _table


def full_id(short):
    """'95517' -> '0450630144' (None if out of range)."""
    if len(short) >= len(ADDER):
        return short
    k = int(short) + ADDER[len(short)]
    t = table()
    return t[k] if k < len(t) and t[k] else None


def short_ids(text):
    return [full_id(s) for s in SHORT.findall(text)]


def evo_ids(text):
    return EVO.findall(text)
