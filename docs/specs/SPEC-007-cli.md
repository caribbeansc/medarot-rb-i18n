# SPEC-007 — Command-line interface

`mrb` is meant to be usable by a translator who has never opened a terminal for
anything else. Running it with no arguments must be enough.

```
$ python mrb.py

  MEDAROT RB — translation toolkit

  Game files    ✓ romfs found      (…/romfs)
  Base cache    ✗ not prepared     (run 2)
  Languages     es 3513/3722 · en 0/3722

  1  Translate            pick a language and edit its text
  2  Prepare game files   one-off, ~5 min
  3  Build a mod
  4  Install into an emulator
  5  Check my translation
  6  Add a language
  7  Diagnose (doctor)
  0  Quit

  >
```

Every menu entry maps to a subcommand, so anything done interactively can be
scripted:

```
python mrb.py setup   [--romfs DIR]
python mrb.py status
python mrb.py prepare
python mrb.py extract [--lang CODE]
python mrb.py sync    LANG
python mrb.py textures LANG
python mrb.py validate LANG
python mrb.py build   LANG [--ascii] [--only STEPS] [--skip STEPS] [--keep]
python mrb.py install LANG [--to DIR]
python mrb.py newlang CODE --name NAME
python mrb.py doctor
```

## Requirements

- **R-1** With no arguments and a TTY, `mrb` shows the menu. With no arguments
  and **no** TTY (pipe, CI), it prints `status` and exits 0 — it never blocks
  waiting for input.
- **R-2** Any subcommand runs without ever prompting; missing information is an
  error with a message that names the flag to pass.
- **R-3** The menu is numeric. No arrow keys, no raw terminal mode, no curses:
  it must work in Windows `cmd.exe`, over SSH and inside a Docker log.
- **R-4** Colour and box drawing are used only when the output is a TTY that is
  not `dumb` and `NO_COLOR` is unset; otherwise output is plain ASCII text.
- **R-5** Every destructive action (overwriting a build, installing over an
  existing mod, deleting a cache) states the exact path and asks for
  confirmation. `--yes` pre-answers, and non-interactive runs require it.
- **R-6** The menu recomputes and shows project state — romfs present, cache
  prepared, per-language progress — every time it is drawn, so it doubles as the
  status display.
- **R-7** Exit codes: `0` success, `1` a step failed, `2` bad usage,
  `3` the game files are missing or unusable.
- **R-8** A long step prints progress that is legible when redirected to a file:
  one line per unit of work at most, no cursor tricks required for correctness.
- **R-9** `Ctrl-C` at any prompt returns to the menu; at the menu it quits with
  code 0, without a traceback.
- **R-10** The interface language of the tool itself is English. Translations of
  the *game* are what the language packs are for.
