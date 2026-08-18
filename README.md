# Medarot Card Robattle RB, in your language

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

**メダロット カードロボトル RB** never left Japan, so it only speaks Japanese.

**What this repository is for:** handing anyone the tooling to translate it,
without reverse-engineering anything themselves. You point it at your own dump,
type your text, and it builds you a mod. Adding a language takes a folder, not
code, and improving a translation that is already here takes a pull request.

It starts out with two translations. Both cover the game's full playable text —
about 2640 Japanese lines. The only thing left in the original is the staff
credits and the crowdfunding backers, which are real names, so those aren't
counted here.

| Language | Text | Artwork | State |
|---|---:|---:|---|
| Español | 100% | 18 | playable, played end to end |
| English | 100% | 18 | playable, played end to end |

Both were written by an LLM, so take them as **a starting point, not a finished
localisation**. 100% means every line is translated, not that every line is
right — the goal is to polish them from here, together. Fixing a line takes a
minute, and every correction reaches everyone. See
[Fix a line](#fix-a-line-or-add-a-language).

> **You need your own copy of the game.** These tools read the files from your own
> dump. They do not contain the game and cannot get it for you. All four
> combinations are tested: Kuwagata Ver. and Kabuto Ver., with or without the v1.1
> update.

---

## Play it — the easy way (no Python, no terminal)

Download the patcher from the
[**latest release**](https://github.com/caribbeansc/medarot-rb-i18n/releases/latest).
It is built automatically from this repository and contains nothing from the
game. Pick the file for your computer:

### Windows

1. Download **`MedarotRB-Patcher-Windows.exe`** and double-click it.
2. The first time, Windows may warn that it doesn't recognise the app (it is
   free software without a paid publisher certificate). Click **More info**,
   then **Run anyway**. The whole source is in this repository if you want to
   check it first.

### macOS

1. Download the app for your Mac: **`…macOS-AppleSilicon.zip`** for an M1/M2/M3
   Mac, or **`…macOS-Intel.zip`** for an older Intel one. Not sure which you
   have?  → menu → *About This Mac*.
2. Double-click the `.zip` to unpack the app, then **right-click it and choose
   Open** (not a normal double-click) the first time. macOS asks once whether
   you're sure — click **Open**. After that it opens like any app. This extra
   step is only because the app isn't signed with a paid Apple certificate.

### Then, on either system

1. Point the patcher at your own copy of the game. Either works:
   - a **backup** — `.xci`, `.nsp`, or the compressed `.xcz` / `.nsz`. The
     patcher unpacks it for you. This needs **your own `prod.keys`** (it looks
     in `~/.switch` and your emulator's key folder automatically; if an update
     `.nsp` needs a title key, add it too). Your keys stay on your machine and
     are never part of the download.
   - a **folder** you already extracted with your emulator's *Extract Data →
     RomFS* — no keys needed at all.
2. Pick a language and click **Build the patch**. The very first build prepares
   a cache and takes 20–60 minutes; it only happens once.
3. Click **Install into emulator**, or **ZIP for SD card** for a real Switch
   running Atmosphère.

## Play it — from source

You need Python 3.10+ ([python.org](https://www.python.org/downloads/); on Windows
tick *Add python.exe to PATH*) and your game's **romfs**: in your emulator,
right-click the game, then **Extract Data** and **RomFS**, into an empty folder.
Other routes are in [docs/SETUP.md](docs/SETUP.md). `python gui.py` opens the
same graphical patcher; the menu below does the same and more from the terminal.

```
git clone https://github.com/caribbeansc/medarot-rb-i18n
cd medarot-rb-i18n
pip install -r requirements.txt
python mrb.py
```

Then work down the menu: **1** (point it at that folder), **2**, **3**, **5**, **6**.
Step 2 reads every file in the game once and can take up to an hour; it is done
once per dump, and every language you build afterwards reuses it. All the slow
steps print progress as they go.

```
  1  Point me at the game  set the romfs folder
  2  Prepare game files    one-off, 20-60 min
  3  Read the game's text  extract tables, labels, textures
  4  Translate             edit text, spreadsheets, publish
  5  Build a mod
  6  Install into an emulator
  7  Package for sharing   emulator folder and Atmosphère SD zip
  8  Add a language
  9  Diagnose              check tools, dump and packs
```

Finally, enable mods for the game in your emulator and start it. **On a real
Switch**, use **7** instead of 6: it writes a ZIP to unpack at the root of your SD
card. If anything goes wrong, `python mrb.py doctor` says what is missing.

## Fix a line, or add a language

`python mrb.py extract` gives you every line of the game with the Japanese on one
side and the translation on the other. Fix what reads wrong, or start a new
language with `python mrb.py newlang fr --name "Français" --like es`. You can also
work in a spreadsheet: `python mrb.py csv fr --pending --out fr.csv`.

```
python mrb.py sync fr        # tidy it up for sharing
python mrb.py validate fr    # catches missing {0}, broken <tags>, overlong lines
python mrb.py build fr
```

Then commit `langs/<lang>/` and open a pull request. Small ones land soonest.
Font settings and artwork with text drawn into it:
[docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md).

## Questions

**Will it break my save?** It changes text and pictures, not game logic. Back up
your saves anyway.

**Which emulators?** Ryujinx, Ryubing, Astris, yuzu, sudachi, Eden, Citron and
Suyu, on Windows, Mac and Linux. Anything else: `install <lang> --to <folder>`.

**Real hardware?** Yes, Atmosphère. Menu option 7, or `package <lang> --zip`.

**Which release, and do I need the update?** Kuwagata Ver. and Kabuto Ver. both
work, with or without the v1.1 update. The two releases ship identical data
tables, and the update only rewrites fifteen lines and adds nine, so the Spanish
pack carries both wordings and the build picks the one your dump actually has. The
tool recognises which release you have and installs the mod under the right game.

**Was AI involved?** Heavily, and it is written down rather than glossed over.
See the [AI collaboration statement](#ai-collaboration-statement).

## AI collaboration statement

Built together with an LLM, against constraints agreed up front: **nine
specifications** with **87 numbered requirements** ([docs/specs/](docs/specs/)),
**302 tests** that each name the requirement they cover, 80% line coverage, and
output checked against four retail dumps. **Every line was reviewed by an
experienced developer, and the game was played through with the mod installed.**

The constraints earned their place: they caught a cell address that collided on
repeated row keys, a cache whose files never reached the mod, and a font fallback
chain that closed on itself. None of that turned up by reading the code.

## No game data, by design

A translation is stored as a reference to a line plus your text, never the
Japanese:

```json
{"row": "Ok", "sub": 0, "col": "text", "src": "8b1a7f22c0d4", "t": "Aceptar"}
```

`src` is a fingerprint: enough to notice when the game's text changes, useless for
reconstructing it. Artwork is stored as the pixels the translation adds, over an
image only you have. A test scans every pack for Japanese and fails if it finds
any, and `sync` refuses to publish it.

On your own machine there are no limits: `extract` gives you the full Japanese next
to each translation, `assets` exports any texture as a PNG, `csv` gives you a
spreadsheet. All of that lives in `work/`, which is never shared.

## For developers

Nine specifications in [docs/specs/](docs/specs/) cover the binary format of the
data tables, patching Unity strings in place, texture deltas, language packs and
the CLI; every numbered requirement is named by a test.
[docs/PIPELINE.md](docs/PIPELINE.md) explains where the text lives and the traps,
including a UnityPy bug that silently corrupts 30 of this game's textures.

```
pip install -r requirements-dev.txt
pytest -m "not game"     # 286 tests on a synthetic dump; no game files needed
pytest                   # + 16 more against your own dump(s)
```

What that suite is for, and what it has caught, is in the
[AI collaboration statement](#ai-collaboration-statement).

## Support

If this made the game playable for you, you can buy me a coffee. Fixing a line
that reads wrong helps just as much.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

## Licence

Code MIT ([LICENSE](LICENSE)); translations CC BY-SA 4.0
([LICENSE-TRANSLATIONS](LICENSE-TRANSLATIONS)). Unofficial fan project, not
affiliated with Imagineer, Rocket Studio, Natsume Atari or Nintendo
([NOTICE](NOTICE)). Please do not open issues or pull requests containing game
files or the original Japanese text.
