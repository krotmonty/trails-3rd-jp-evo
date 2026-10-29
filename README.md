# Trails in the Sky the 3rd: Japanese text with Evo voices, ready for Yomitan

Play the English Steam release of *The Legend of Heroes: Trails in the Sky the 3rd* with the Evo
voice mod, but with **Japanese text**, and read every line on a local web page where
[Yomitan](https://github.com/yomidevs/yomitan) can scan it. Cards you mine get the line's voice
clip and a screenshot.

- **Dialogue in Japanese, matching the voices.** Voiced lines use the Evo (Vita) script, matched
  by voice ID, so the text is what the actor says. Unvoiced lines use the Japanese PC script.
- **Choices, speaker names, menus, items, skills, quests, books, recipes, monsters and the monster
  notebook** in Japanese, keeping the English release's balance data (XSEED's rebalanced crafts,
  stats and added items stay). One switch flips all of these back to English.
- **Minigames** (fishing, quiz, poker) in Japanese with their Evo voices.
- **A reading page** at `http://localhost:6677`: the current line large in Japanese, the English
  below (show / blur / off), history. Or an **overlay strip** over the bottom of the game.
  It also feeds [texthooker-ui](https://github.com/Renji-XD/texthooker-ui) (WebSocket on the same
  port).
- **Anki**: when you add a card with Yomitan while playing, the line's voice clip goes into the
  sentence audio field and a screenshot of the game into the picture field.

No game files are included here. Everything is built on your PC from your own game, the voice mod
and the Japanese script packs.

## What you need

1. **Trails in the Sky the 3rd** on Steam (English).
2. **The SoraVoice Lite Evo voice mod** for the 3rd, installed and working (voices play in game).
   This mod builds on it and replaces its `ed_voice.dll` with an extended one.
3. **The Japanese PC script packs** `ED6the3rd-JP-Script.7z` and `ED6the3rd-JP-Script-DT30.7z`
   (from the first download on modding.tistory.com/55). Extract them so that these folders exist:
   `downloads/jp-script/ED6_DT21`, `ED6_DT22`, `ED6_DT30`, `ED6_DT3C`.
4. **Python 3.12+** and **git**.
5. **Visual Studio 2022 Build Tools** with the C++ workload, to build the DLL. Or skip that with a
   prebuilt `ed_voice.dll` (see Releases) and `--dll`.

## Install

From this folder:

```bash
python -m venv tools/venv
tools/venv/Scripts/python.exe tools/build.py
```

The first run downloads the tools it needs (SoraVoice, SoraVoiceScripts, SoraVoice-Tools,
EDDecompiler, PyLibs) into `src/` at fixed versions, backs up the voice mod's files to
`backup/mod-original`, builds everything into `build/` and installs it. Close the game first.
It takes about 10 minutes. Options:

- `--game "D:\Steam\steamapps\common\Trails in the Sky the 3rd"` if the game isn't found.
- `--dll path\to\ed_voice.dll` to use a prebuilt DLL instead of building it.
- `--no-install` to only build.

Run it again after a Steam update or file verification; it reinstalls everything.

**Uninstall:** `tools/venv/Scripts/python.exe tools/build.py uninstall` puts the voice mod's
original files back.

## Use

**The page.** Start the game; the page opens by itself as an Edge app window next to the game
(or as the overlay strip, see settings). You can also open `http://localhost:6677` in any browser.
Yomitan scans it like any page. With the game focused, set Yomitan to scan on hover or with a
mouse button, since the browser doesn't see keyboard modifiers.

**Game resolution.** Pick a resolution in `Config3_DX9.exe` (windowed) that leaves room for the
page, e.g. 1280×720 on a 1920×1080 screen. Don't resize the game window from outside.

**JP/EN switch.** Double-click `Menu text JP-EN.bat` in the game folder (game closed) to switch
menus, names, items, skills, quests, books, recipes and monsters between Japanese and English.
Dialogue stays Japanese.

**Settings** in `voice\ed_voice.ini` (written on first start):

| Setting | Meaning |
|---|---|
| `TextFeed` | 1 = reading page and feed on, 0 = off |
| `TextFeedPort` | port of the page (6677) |
| `OpenPage` | open the page window when the game starts |
| `PageBrowser` | 0 = Edge, 1 = Chrome (use the one with Yomitan) |
| `PageMode` | 0 = window docked beside the game, with history; 1 = overlay strip |
| `OverlayOpacity`, `OverlayHeight` | the strip's opacity (%) and height (px) |
| `OverlayExpandKey`, `OverlayExpandHeight` | key (F9 = 120) that grows the strip so Yomitan's popup fits |
| `WindowX`, `WindowY` | game window position (-1 = leave) |

**Anki.** Needs [AnkiConnect](https://ankiweb.net/shared/info/2055492159) with
`http://localhost:6677` in its `webCorsOriginList`. The note type and field names are at the top of
the script in `voice\web\index.html` (`ANKI`: port, model, audio, picture and sentence fields;
defaults: port 8080, `Lapis`, `SentenceAudio`, `Picture`, `Sentence`). Only empty fields of cards
added while the game runs are filled. Keep the card closed in Anki's browser for a second after
adding it, or Anki can overwrite the change.

## What stays English

- XSEED additions with no Japanese original: a few items, a quest, a quiz difficulty, a few
  monster craft names.
- Menu headings and labels drawn by the game's exe and images (e.g. "Elemental Efficacy").
- About 500 dialogue pages, mostly in developer test maps.

## How it works

- `tools/jpify.py` rewrites the decompiled English voiced scripts: each page keeps its voice cue
  and control codes and gets Japanese text. `tools/check.py` refuses any file whose commands,
  voice cues or voice-to-text match differ from English; those stay English.
- `tools/tables.py`, `tools/monsters.py`, `tools/minigames.py` merge Japanese text into the
  English data files, keeping English data.
- `patches/soravoice-yomitan.patch` extends SoraVoice: a text hook feeding the page, a small
  HTTP/WebSocket server (page, voice clips, screenshots), window placement, the overlay, and
  loading battle and notebook files.

## Credits

- [SoraVoice](https://github.com/ZhenjianYang/SoraVoice), SoraVoiceScripts, SoraVoice-Tools,
  [EDDecompiler](https://github.com/ZhenjianYang/EDDecompiler) and PyLibs by ZhenjianYang; the Evo
  voice project.
- The Japanese PC script packs from modding.tistory.com.
- Falcom and XSEED for the game.

The SoraVoice patch and any `ed_voice.dll` built from it are under SoraVoice's license (GPL-3.0).
