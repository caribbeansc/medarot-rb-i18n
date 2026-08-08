# Setup

You need three things: Python, this repository, and the game files from **your
own** dump. About fifteen minutes, most of it waiting.

## 1. Python 3.10 or newer

| Platform | How |
|---|---|
| Windows | [python.org](https://www.python.org/downloads/) — tick *Add python.exe to PATH* |
| macOS | `brew install python` (or python.org) |
| Linux | `sudo apt install python3 python3-pip python3-venv` (or your package manager) |

Check it:

```
python --version        # Windows
python3 --version       # macOS / Linux
```

## 2. This repository and its dependencies

```
git clone https://github.com/caribbeanwebdev/medarot-rb-i18n
cd medarot-rb-i18n

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

The virtual environment is optional but keeps things tidy. Without it, use
`pip install --user -r requirements.txt`.

## 3. The game files

The tools need the game's **romfs**: the extracted data of your own cartridge or
dump. All four combinations are tested — Kuwagata Ver. and Kabuto Ver., each with
and without the v1.1 update.

With the update you get nine extra lines of menu text that the base game does not
have; everything else is the same. If you switch between a base-only dump and an
updated one, run `extract` and `prepare` again: they share a title id, so the tool
compares a fingerprint of the files and warns you if the cache came from the other
one. Pick whichever route you already have set up.

### From an emulator (easiest)

Ryujinx-family and yuzu-family emulators can do this from the game list:

1. Make sure the **update** is installed alongside the base game.
2. Right-click the game → **Extract Data** → **RomFS**.
3. Choose an empty folder.

You end up with a folder containing `Data/`, and inside it
`Data/StreamingAssets/`. That folder is your romfs.

### From an XCI/NSP with hactoolnet

```
hactoolnet -k prod.keys -t xci  --romfsdir=romfs_base   base.xci
hactoolnet -k prod.keys -t pfs0 --outdir=update_ncas    update.nsp
```

The update's program NCA has to be applied on top of the base one; if that is new
to you, the emulator route above is much less painful.

### What "good" looks like

```
your-romfs/
└── Data/
    ├── StreamingAssets/
    │   ├── IdxResData/IdxRes_CardDef.bytes    ← 107 of these
    │   └── aa/Switch/*.bundle                 ← ~1500 of these
    ├── level0 … level4
    └── sharedassets0.assets …
```

## 4. Point the tool at it

```
python mrb.py setup --romfs /path/to/your-romfs
python mrb.py doctor
```

`setup` recognises which release you have — Kuwagata Ver. or Kabuto Ver. — and
sets the title id for you, so the mod installs under the right game. Override it
with `--title-id` if you have something it does not know.

Both releases ship the same data tables, so a translation works on either. You can
keep both dumps side by side: everything derived from a dump lives under
`work/<title id>/`, and `MEDAROT_ROMFS` plus `MEDAROT_TITLE_ID` override the saved
configuration for one command.

`doctor` tells you what it found and what is missing. If it lists your tables,
bundles and scene files, you are done. From here on, just run:

```
python mrb.py
```

## Notes per platform

**Windows.** Use `python mrb.py`, and quote paths with spaces:
`python mrb.py setup --romfs "C:\games\medarot romfs"`. The menu works in
`cmd.exe`, PowerShell and Windows Terminal.

**macOS.** If `python` is not found, use `python3`. Astris keeps its Ryujinx data
inside an app container; `mrb install` already knows where.

**Linux.** Flatpak emulators keep their data under `~/.var/app/...`;
`mrb doctor` will show it if it is detected, and `mrb install --to <dir>` covers
anything it misses.

## Where things end up

| Path | What | Committed? |
|---|---|---|
| `mrb.config.json` | the path to your romfs | no |
| `work/<title id>/` | source text, inventories, PNG exports, caches, one folder per dump | no |
| `build/` | the generated mods | no |
| `langs/` | the translations themselves | **yes** |

`work/` is where the game's own text lives on your machine. It is in
`.gitignore` and must stay there.
