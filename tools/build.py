"""Build and install the Japanese text mod for Trails in the Sky the 3rd (English Steam + Evo voices).

Usage (from the project folder, with the venv Python):
  python tools/build.py               build everything and install it into the game
  python tools/build.py --no-install  build only (into build/)
  python tools/build.py uninstall     put the voice mod's original files back
Options:
  --game DIR   the game folder (default: found through Steam)
  --dll FILE   use this ed_voice.dll instead of building it (no Visual Studio needed)

Needs, besides this folder: the game with the SoraVoice Lite Evo voice mod installed, the Japanese
PC script packs extracted to downloads/jp-script (see README), Python 3.12+ and git. Building the
DLL needs Visual Studio 2022 Build Tools (C++); --dll skips that.
"""

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SRC = os.path.join(ROOT, "src")
BUILD = os.path.join(ROOT, "build")
JP = os.path.join(ROOT, "downloads", "jp-script")
BACKUP = os.path.join(ROOT, "backup", "mod-original")
PY = sys.executable
GAME_NAME = "Trails in the Sky the 3rd"

REPOS = {  # name: (url, pinned commit)
    "SoraVoice": ("https://github.com/ZhenjianYang/SoraVoice.git", "4b97d92"),  # tag 20230823
    "SoraVoiceScripts": ("https://github.com/ZhenjianYang/SoraVoiceScripts.git", "94a9480"),
    "SoraVoice-Tools": ("https://github.com/ZhenjianYang/SoraVoice-Tools.git", "afa2350"),
    "EDDecompiler": ("https://github.com/ZhenjianYang/EDDecompiler.git", "4bca642"),
    "PyLibs": ("https://github.com/ZhenjianYang/PyLibs.git", "4811a38"),
}
# PyLibs fixes: Python 3.10+ moved the collection ABCs; a failed compile must exit, not wait for a key
PYLIBS_FIXES = [
    ("ouroboros/otypes/OrderedSet.py", "import collections\n", "import collections, collections.abc\n"),
    ("ouroboros/otypes/OrderedSet.py", "(collections.MutableSet)", "(collections.abc.MutableSet)"),
    ("ouroboros/otypes/CaseInsensitiveDict.py", "import collections\n", "import collections, collections.abc\n"),
    ("ouroboros/otypes/CaseInsensitiveDict.py", "collections.Iterable", "collections.abc.Iterable"),
    ("ouroboros/console/console.py", "        print(text)\n    getch()",
     "        print(text)\n    if os.environ.get('ED_NOPAUSE'):  # batch builds: fail instead of waiting for a key\n"
     "        sys.exit(1)\n    getch()"),
]
MG_FILES = ["T_FISH  ._DT", "T_QUIZ01._DT", "T_QUIZ02._DT", "T_QUIZ03._DT", "T_QUIZ04._DT",
            "Z_POKER8._DT", "Z_POKER9._DT"]


def step(title):
    print(f"\n== {title}", flush=True)


def run(args, cwd=ROOT, env=None, quiet=False):
    r = subprocess.run(args, cwd=cwd, env=env, capture_output=quiet, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        if quiet:
            print(r.stdout, r.stderr)
        raise SystemExit(f"failed: {' '.join(map(str, args))}")
    return r


def find_game():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = winreg.QueryValueEx(k, "SteamPath")[0]
    except OSError:
        return None
    libraries = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        libraries += re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8").read())
    for lib in libraries:
        game = os.path.join(lib.replace("\\\\", "\\"), "steamapps", "common", GAME_NAME)
        if os.path.isdir(game):
            return os.path.normpath(game)
    return None


def scena_env():
    env = dict(os.environ, ED_NOPAUSE="1", PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = os.pathsep.join([os.path.join(SRC, "EDDecompiler", "Decompiler"), os.path.join(SRC, "PyLibs")])
    return env


# ---- steps ------------------------------------------------------------------------------------

def setup():
    step("Tools (cloned at pinned versions, patched)")
    os.makedirs(SRC, exist_ok=True)
    for name, (url, commit) in REPOS.items():
        path = os.path.join(SRC, name)
        if not os.path.isdir(path):
            run(["git", "clone", "-q", url, path])
            run(["git", "-C", path, "checkout", "-q", commit])
            if name == "SoraVoice":
                run(["git", "-C", path, "apply", os.path.join(ROOT, "patches", "soravoice-yomitan.patch")])
    for rel, old, new in PYLIBS_FIXES:
        path = os.path.join(SRC, "PyLibs", rel)
        text = open(path, encoding="utf-8", newline="").read()
        nl = "\r\n" if "\r\n" in text else "\n"
        old_, new_ = old.replace("\n", nl), new.replace("\n", nl)
        if new_ not in text:
            if old_ not in text:
                raise SystemExit(f"PyLibs: cannot apply fix to {rel}")
            open(path, "w", encoding="utf-8", newline="").write(text.replace(old_, new_))
    for d in ("ED6_DT21", "ED6_DT22", "ED6_DT30", "ED6_DT3C"):
        if not os.path.isdir(os.path.join(JP, d)):
            raise SystemExit(f"missing {os.path.join(JP, d)}: extract the Japanese script packs there (README)")
    print("ok")


def backup(game):
    step("Backup of the voice mod's own files")
    if os.path.isdir(BACKUP):
        print("exists:", BACKUP)
        return
    voice = os.path.join(game, "voice")
    if not os.path.exists(os.path.join(voice, "ed_voice.dll")):
        raise SystemExit("the SoraVoice Lite Evo voice mod is not installed in the game folder")
    if os.path.isdir(os.path.join(voice, "web")):
        raise SystemExit("the game already has this mod installed but no backup exists; reinstall the voice mod first")
    os.makedirs(os.path.join(BACKUP, "voice"))
    shutil.copytree(os.path.join(voice, "scena"), os.path.join(BACKUP, "voice", "scena"))
    for f in ("ed_voice.dll", "ed_voice.ini"):
        shutil.copy2(os.path.join(voice, f), os.path.join(BACKUP, "voice", f))
    print("saved to", BACKUP)


def decompile(game):
    step("Decompile English (voiced) and Japanese scripts")
    script = os.path.join(SRC, "EDDecompiler", "Decompiler", "ED63RDScenarioScript.py")
    for name, src in (("en_voiced", os.path.join(BACKUP, "voice", "scena")), ("jp_pc", os.path.join(JP, "ED6_DT21"))):
        out = os.path.join(BUILD, name)
        sns = [f for f in os.listdir(src) if f.endswith("._SN")]
        if os.path.isdir(out) and len([f for f in os.listdir(out) if f.endswith(".py")]) >= len(sns):
            print(name, "already decompiled")
            continue
        os.makedirs(out, exist_ok=True)
        for f in sns:
            shutil.copy2(os.path.join(src, f), os.path.join(out, f))
        run([PY, script, "--cp=ms932", f"--gp={game}", out], cwd=BUILD, env=scena_env(), quiet=True)
        print(name, len(sns), "files")


def dialogue(game):
    step("Dialogue, choices and names (jpify, compile, check)")
    msg = os.path.join(SRC, "SoraVoiceScripts", "en.3rd", "out.msg")
    jp_py, jp_sn = os.path.join(BUILD, "jp_py"), os.path.join(BUILD, "jp_sn")
    shutil.rmtree(jp_py, ignore_errors=True)
    shutil.rmtree(jp_sn, ignore_errors=True)
    os.makedirs(jp_sn)
    run([PY, os.path.join(TOOLS, "jpify.py"), os.path.join(BUILD, "en_voiced"), msg, os.path.join(BUILD, "jp_pc"),
         jp_py, os.path.join(BUILD, "jpify-report.json")], env=scena_env())
    env = scena_env()

    def compile_one(f):
        log = os.path.join(jp_py, f + ".log")
        with open(log, "w", encoding="utf-8") as fh:
            try:
                subprocess.run([PY, os.path.join(jp_py, f), "--cp=ms932", f"--gp={game}", jp_sn], cwd=BUILD,
                               env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
            except subprocess.TimeoutExpired:
                pass
        return f
    files = [f for f in os.listdir(jp_py) if f.endswith(".py")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        list(pool.map(compile_one, files))
    print(len(os.listdir(jp_sn)), "of", len(files), "compiled")
    run([PY, os.path.join(TOOLS, "check.py"), os.path.join(BUILD, "en_voiced"), jp_py, jp_sn,
         os.path.join(BUILD, "jp_pc"), msg, os.path.join(BUILD, "check-report.json")], env=scena_env())


def tables(game):
    step("Menus, names, items, skills, quests, books (tables)")
    run([PY, os.path.join(TOOLS, "tables.py"), os.path.join(game, "ED6_DT22.dir"), os.path.join(JP, "ED6_DT22"),
         os.path.join(BUILD, "tables_jp"), os.path.join(BUILD, "Menu text JP-EN.bat")])


def monsters(game):
    step("Monsters and the monster notebook")
    out = os.path.join(BUILD, "ms_jp")
    shutil.rmtree(out, ignore_errors=True)
    run([PY, os.path.join(TOOLS, "monsters.py"), os.path.join(game, "ED6_DT30.dir"), os.path.join(JP, "ED6_DT30"),
         os.path.join(game, "ED6_DT3C.dir"), os.path.join(JP, "ED6_DT3C", "MNSNOTE2._DT"), out])


def minigames():
    step("Minigames (fishing, quiz, poker)")
    py_tools = os.path.join(SRC, "SoraVoice-Tools", "src", "Py")
    inst, jp_txt, dt = (os.path.join(BUILD, d) for d in ("mg_installed", "mg_jp", "mg_dt"))
    for d in (inst, jp_txt, dt):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    orig = os.path.join(BACKUP, "voice", "scena")
    for q in ("01", "02", "03", "04"):
        run([PY, "-I", os.path.join(py_tools, "Quiz2Txt.py"), "--cp=ms932", os.path.join(orig, f"T_QUIZ{q}._DT"), inst])
    shutil.copy2(os.path.join(orig, "T_FISH  ._DT"), inst)  # Fish2Txt writes next to its input
    run([PY, "-I", os.path.join(py_tools, "Fish2Txt.py"), "--cp=ms932", os.path.join(inst, "T_FISH  ._DT")])
    os.remove(os.path.join(inst, "T_FISH  ._DT"))
    pc = os.path.join(BUILD, "mg_pc")
    os.makedirs(pc, exist_ok=True)
    for q in ("01", "02", "03", "04"):
        run([PY, "-I", os.path.join(py_tools, "Quiz2Txt.py"), "--cp=ms932", os.path.join(JP, "ED6_DT22", f"T_QUIZ{q}._DT"), pc])
    run([PY, os.path.join(TOOLS, "minigames.py"), inst, os.path.join(SRC, "SoraVoiceScripts", "en.3rd", "mg.txt.evo"),
         pc, orig, jp_txt])
    for q in ("01", "02", "03", "04"):
        run([PY, "-I", os.path.join(py_tools, "Txt2Quiz.py"), "--cp=ms932", os.path.join(jp_txt, f"T_QUIZ{q}.txt"), dt])
    run([PY, "-I", os.path.join(py_tools, "Txt2Fish.py"), "--cp=ms932", os.path.join(orig, "T_FISH  ._DT"),
         os.path.join(jp_txt, "T_FISH.txt"), dt])
    for p in ("Z_POKER8._DT", "Z_POKER9._DT"):
        shutil.copy2(os.path.join(jp_txt, p), dt)


def page():
    step("Reading page (English lookup)")
    run([PY, os.path.join(TOOLS, "enlookup.py"), os.path.join(BUILD, "en_voiced"), os.path.join(BUILD, "jp_py"),
         os.path.join(ROOT, "web", "en.json")])


def dll(given):
    step("ed_voice.dll (SoraVoice with the Yomitan feed)")
    out = os.path.join(BUILD, "ed_voice.dll")
    if given:
        shutil.copy2(given, out)
        print("using", given)
        return
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    msbuild = None
    if os.path.exists(vswhere):
        r = subprocess.run([vswhere, "-products", "*", "-find", r"MSBuild\**\Bin\MSBuild.exe"], capture_output=True, text=True)
        msbuild = (r.stdout.splitlines() or [None])[0]
    if not msbuild:
        raise SystemExit("Visual Studio Build Tools not found: install them, or pass --dll with a prebuilt ed_voice.dll")
    sol = os.path.join(SRC, "SoraVoice", "solution")
    run([msbuild, os.path.join(sol, "ed_voice", "ed_voice.vcxproj"), "-p:Configuration=Release", "-p:Platform=Win32",
         f"-p:SolutionDir={sol}{os.sep}", "-m", "-v:minimal"], quiet=True)
    shutil.copy2(os.path.join(SRC, "SoraVoice", "bin", "Release", "ed_voice.dll"), out)
    print("built")


def game_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ed6_win3_DX9.exe"], capture_output=True, text=True)
    r2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ed6_win3.exe"], capture_output=True, text=True)
    return "ed6_win3" in (r.stdout + r2.stdout)


def install(game):
    step("Install into the game")
    if game_running():
        raise SystemExit("close the game first")
    import json
    voice = os.path.join(game, "voice")
    scena, parked = os.path.join(voice, "scena"), os.path.join(voice, "jp-options")
    os.makedirs(parked, exist_ok=True)
    # menu tables and monsters go where the JP/EN switch currently keeps them
    menu_dest = parked if os.path.exists(os.path.join(parked, "T_MAGIC ._DT")) else scena
    problems = json.load(open(os.path.join(BUILD, "check-report.json"), encoding="utf-8"))["problems"]
    n = kept = 0
    for f in os.listdir(os.path.join(BUILD, "jp_sn")):
        if f.split(".")[0].strip() in problems:
            kept += 1
            continue
        shutil.copy2(os.path.join(BUILD, "jp_sn", f), scena)
        n += 1
    for d in ("tables_jp", "ms_jp"):
        for f in os.listdir(os.path.join(BUILD, d)):
            shutil.copy2(os.path.join(BUILD, d, f), menu_dest)
    for f in os.listdir(os.path.join(BUILD, "mg_dt")):
        shutil.copy2(os.path.join(BUILD, "mg_dt", f), scena)
    os.makedirs(os.path.join(voice, "web"), exist_ok=True)
    for f in ("index.html", "en.json"):
        shutil.copy2(os.path.join(ROOT, "web", f), os.path.join(voice, "web"))
    shutil.copy2(os.path.join(BUILD, "ed_voice.dll"), voice)
    shutil.copy2(os.path.join(BUILD, "Menu text JP-EN.bat"), game)
    print(f"dialogue: {n} files Japanese, {kept} kept English (failed the check)")
    print("menus/monsters:", "Japanese" if menu_dest == scena else "English (switch is on English)")


def uninstall(game):
    step("Uninstall: put the voice mod's original files back")
    if game_running():
        raise SystemExit("close the game first")
    if not os.path.isdir(BACKUP):
        raise SystemExit("no backup found")
    voice = os.path.join(game, "voice")
    shutil.rmtree(os.path.join(voice, "scena"))
    shutil.copytree(os.path.join(BACKUP, "voice", "scena"), os.path.join(voice, "scena"))
    for f in ("ed_voice.dll", "ed_voice.ini"):
        shutil.copy2(os.path.join(BACKUP, "voice", f), voice)
    for d in ("web", "jp-options"):
        shutil.rmtree(os.path.join(voice, d), ignore_errors=True)
    bat = os.path.join(game, "Menu text JP-EN.bat")
    if os.path.exists(bat):
        os.remove(bat)
    print("done: the game is back to the English voice mod")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="build", choices=["build", "uninstall"])
    ap.add_argument("--game")
    ap.add_argument("--dll")
    ap.add_argument("--no-install", action="store_true")
    a = ap.parse_args()
    game = a.game or find_game()
    if not game or not os.path.exists(os.path.join(game, "ED6_DT22.dir")):
        raise SystemExit("game folder not found: pass --game")
    print("game:", game)
    if a.command == "uninstall":
        return uninstall(game)
    os.makedirs(BUILD, exist_ok=True)
    setup()
    backup(game)
    decompile(game)
    dialogue(game)
    tables(game)
    monsters(game)
    minigames()
    page()
    dll(a.dll)
    if not a.no_install:
        install(game)
    print("\nAll done.")


if __name__ == "__main__":
    main()
