# Contributing

Two kinds of contribution, with different rules: **translations** and **code**.

## The one hard rule

**Never commit anything that came out of the game.** Not the Japanese script, not
a texture, not a bundle, not a screenshot of the original text in an issue.

This is what keeps the repository redistributable, and it is enforced, not
trusted:

```
python mrb.py doctor        # scans langs/ for source text
pytest tests/test_packs.py  # the same check, as a test
```

`mrb sync` refuses to publish a translation that still contains Japanese, and
`work/`, `build/` and `mrb.config.json` are in `.gitignore`. Leave them there.

## Translations

Start from [docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md). Before opening
a pull request:

```
python mrb.py sync <lang>
python mrb.py validate <lang>
python mrb.py doctor
```

- Commit only `langs/<lang>/`.
- Fix every error `validate` reports. Warnings are judgement calls: a "may
  overflow" on a card name is worth checking in game, on a tutorial paragraph it
  usually is not.
- Say who you are and how the text was produced in the pull request, and add a
  line to the language table in the README. If it was machine-generated, say so,
  and say how much of it you checked. An honest "generated, skimmed, not
  play-tested" is far more useful to the next person than silence.

Improving an existing language is just as welcome as adding a new one. Small,
focused pull requests ("fix 30 card names in CardDef") are easier to review than
one that rewrites everything.

## Code

The project is **spec-first**. Every non-obvious behaviour is a numbered
requirement in [docs/specs/](docs/specs/), and every requirement has at least one
test that names it.

So, in order:

1. Change the spec, in its own commit, if the behaviour changes.
2. Add or update the test that references the requirement (`SPEC-006/R-4`).
3. Change the implementation.

```
pip install -r requirements-dev.txt
pytest -m "not game"       # no game files needed; must stay green
pytest                     # includes the tests that need your own dump
```

House rules that are not negotiable, because each one has burned this project
once:

- **Never call `UnityPy.load` directly.** Import `medarot.unity` — it applies the
  Switch swizzle fix first. A test scans the source tree for violations.
- **Re-inject textures with `target_format=d.m_TextureFormat`.** Letting the
  library pick breaks ASTC 5x5.
- **Read back what you wrote.** Every patch step re-opens its output and verifies
  the values before the build is called a success.
- **Do not reorder build steps.** Later steps read what earlier ones wrote.
- **Never overwrite a translation with an empty string.** Extraction merges, it
  does not replace.

Style: the code reads like prose and the comments explain *why*, not *what*.
Docstrings and identifiers are in English so contributors who do not speak Spanish
can work on it; the language packs are where other languages live.

## Reporting a bug

Include:

- what you ran, and the output;
- your platform and Python version (`python mrb.py doctor` prints both);
- whether the game files came from an emulator extraction or hactoolnet.

Do not attach game files or the original Japanese text.
