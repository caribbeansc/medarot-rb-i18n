# Medarot Card Robattle RB, in your language

**メダロット カードロボトル RB** never left Japan, so it only speaks Japanese.

**What this repository is for:** handing anyone the tooling to translate it,
without reverse-engineering anything themselves. You point it at your own dump,
type your text, and it builds you a mod. Adding a language takes a folder, not
code.

It also ships translations:

| Language | Text | Artwork | State |
|---|---:|---:|---|
| Español | 3823 / 4032 | 18 | playable |
| English | 0 / 4032 | 0 | template, every line waiting |

**Those translations were written entirely by an LLM** and validated by their
author playing the game through, finding nothing badly broken. Take them as a
**reference, not as a high-quality, error-free translation**: they are a way to
play a game that has none, and a starting point to correct. If you find something
wrong, fix it. That is what the tooling is for.

> **You need your own copy of the game.** These tools read the files from your own
> dump. They do not contain the game and cannot get it for you. All four
> combinations are tested: Kuwagata Ver. and Kabuto Ver., with or without the v1.1
> update.

---

## Play it

You need Python 3.10+ ([python.org](https://www.python.org/downloads/); on Windows
tick *Add python.exe to PATH*) and your game's **romfs**: in your emulator,
right-click the game, then **Extract Data** and **RomFS**, into an empty folder.
Other routes are in [docs/SETUP.md](docs/SETUP.md).

```
git clone https://github.com/caribbeanwebdev/medarot-rb-i18n
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

## Translate it into your language

```
python mrb.py newlang fr --name "Français" --like es
python mrb.py extract
```

Your working copy now holds every line of the game with the Japanese on one side
and an empty slot for your text on the other. Fill it in from the menu, from a
spreadsheet (`python mrb.py csv fr --pending --out fr.csv`), or in your editor.
Then:

```
python mrb.py sync fr        # tidy it up for sharing
python mrb.py validate fr    # catches missing {0}, broken <tags>, overlong lines
python mrb.py build fr
```

Full walkthrough, including the font settings your language probably needs and how
to translate artwork with text drawn into it:
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

**Was AI involved?** Heavily, and it is written down rather than glossed over. The
tools were built by an LLM against the specifications in [docs/specs/](docs/specs/),
with tests as the constraint; the translations were generated the same way and
checked by playing.

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
pytest -m "not game"     # 285 tests on a synthetic dump; no game files needed
pytest                   # + 16 more against your own dump(s)
```

301 tests, 80% line coverage. Verified against four real dumps — both releases,
each with and without the update: every data table round-trips byte-for-byte, the
Spanish pack covers every translatable cell in all four, and the built mod matches
the reference pipeline file for file.

## Licence

Code MIT ([LICENSE](LICENSE)); translations CC BY-SA 4.0
([LICENSE-TRANSLATIONS](LICENSE-TRANSLATIONS)). Unofficial fan project, not
affiliated with Imagineer, Rocket Studio, Natsume Atari or Nintendo
([NOTICE](NOTICE)). Please do not open issues or pull requests containing game
files or the original Japanese text.
