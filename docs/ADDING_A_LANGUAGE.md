# Adding a language

A language is a folder under `langs/`. You do not need to touch any Python.

## 1. Create the pack

```
python mrb.py newlang fr --name "Français" --like es
```

`--like es` copies the *key list* from Spanish, with the translations blank, so
you start with the full inventory of what there is to translate instead of an
empty folder. It never copies anyone's translation.

You get:

```
langs/fr/
├── lang.json                 metadata and behaviour switches
├── idxres/*.json             one file per data table, 3722 keys in total
├── labels.json               405 labels serialized in bundles and scenes
├── textures/textures.json    the 18 textures with text baked into the artwork
└── textures/delta/           empty until you translate a texture
```

## 2. Tell the tool what your language needs

Edit `langs/fr/lang.json`:

```json
{
  "code": "fr",
  "name": "Français",
  "english_name": "French",
  "mod_name": "MedarotRB_FR",
  "font": {
    "fallbacks": ["FOT-CezannePro-DB SDF", "LiberationSans SDF"],
    "global_fallbacks": true,
    "neutralize_kerning": true,
    "fix_tmp_metrics": true
  },
  "validation": {
    "extra_chars": "àâçéèêëîïôùûüÿœÀÂÇÉÈÊËÎÏÔÙÛÜŸŒ«»-…♪↑↓",
    "max_line": 46,
    "length_factor": 1.25
  },
  "ascii_fallback": { "à": "a", "é": "e", "ç": "c", "œ": "oe" }
}
```

What each switch does:

- **`font.fallbacks`**: the game's two main fonts have no accented glyphs. Any
  language that needs them lists, *by name*, fonts in the game that do:
  `FOT-CezannePro-DB SDF` and `LiberationSans SDF` both carry a complete Latin
  set. English needs none of this; French, Portuguese and German do.
- **`font.global_fallbacks`**: also fill TextMeshPro's global fallback list, so
  any font you did not think of is covered too.
- **`font.neutralize_kerning`**: the game ships kerning pairs tuned for Japanese
  that overlap Latin letters. Leave this on for any Latin-script language.
- **`font.fix_tmp_metrics`**: undo the negative letter spacing and glyph
  squeezing. Leave it on unless your language really is fixed-width.
- **`validation.extra_chars`**: every non-ASCII character your language is
  allowed to use. Anything else is reported as an error, which is how typos and
  stray characters get caught.
- **`ascii_fallback`**: used only by `mrb build --ascii`, for players whose font
  patch did not take.

## 3. Get the source text

```
python mrb.py extract
```

This reads **your** dump and writes `work/<title id>/lang/fr/`, where each entry has the
original Japanese next to an empty translation:

```json
{"row": "Ok", "sub": 0, "col": "text", "src": "8b1a7f22c0d4",
 "jp": "<the Japanese from your dump>", "t": ""}
```

`work/` is gitignored: that is the only place the game's text lives, and it stays
on your machine. It is keyed by title id, so the two releases of the game never
mix.

## 4. Translate

Three ways, use whichever you like:

**In the terminal.** `python mrb.py` → *Translate* → *Translate here*. It shows
one string at a time. `.q` saves and quits, `.s` skips the rest of a table.

**In a spreadsheet.**

```
python mrb.py csv fr --pending --out fr.csv
# edit the 'translation' column in Excel / LibreOffice / Sheets
python mrb.py csv fr --import fr.csv
```

**In your editor.** Open `work/<title id>/lang/fr/idxres/Text_Menu.json` and fill in `t`.

Rules that matter:

- Keep `{0}`, `{1}` placeholders exactly as they are.
- Keep TextMeshPro tags (`<color=#…>`, `<size=…>`, `<nobr>`) exactly as they are.
- Translate inside `【…】`, keep the brackets.
- Use `\n` for line breaks. Menu labels and buttons are tight, so keep those
  under ~46 characters.
- **Card skill texts (`CardDef` `m_skillText1/2`) need manual `\n` breaks.**
  The card detail panels auto-size instead of word-wrapping: a long text
  without `\n` gets squeezed into a single line that spills past the panel,
  and a manual line wider than the panel either gets crammed or re-wraps
  leaving orphan words. Keep every line at ~40 characters or less (35 units
  of the proportional model in `tools/rewrap_cards.py` — run it to re-break
  a whole language automatically), and keep skill1 + skill2 to 6 lines total
  (8 if the card only has one block). That is the JP designer's own spec,
  found in the placeholder text of the panel component.
- The keyword description panel (`KeyWordDef` and `BuffWordDef` `m_text`)
  is wider: it fits 3 lines of ~92. Raise `max_line` in `lang.json` to match
  the longest panel you actually use.
- Do not translate text the game already shows in English (`New Record`, `MAX`).

Good places to start, in order of impact per string: `Text_Menu` (186),
`Text_Battle` (65), `Text_Tutorial` (312), `SkillDef` (368), `CardDef` (1078).

## 5. Publish, check, build

```
python mrb.py sync fr        # work/ -> langs/, dropping the source text
python mrb.py validate fr    # placeholders, markup, charset, length
python mrb.py build fr
python mrb.py install fr
```

`sync` is what makes your work committable: it writes only keys, fingerprints and
translations. If anything Japanese slipped into a translation, it refuses.

## 6. Artwork with text baked in (optional)

Eighteen textures have text drawn into the image. To do one:

```
python mrb.py assets --list --filter Card       # find the exact name
python mrb.py assets --name Card_Change         # export the PNG
# edit the exported PNG in any image editor, then import it back
python mrb.py textures fr --import work/<title id>/assets/dlg/Card_Change.png
python mrb.py textures fr --preview Card_Change # look at the result
```

Only the pixels you changed are stored, as an overlay plus a mask. See
[specs/SPEC-003](specs/SPEC-003-texture-delta.md).

## 7. Open a pull request

```
python mrb.py doctor         # confirms no source text made it into langs/
git add langs/fr
git commit -m "Add French translation"
```

Please do not commit `work/`, `build/` or `mrb.config.json`; `.gitignore` already
excludes them. See [../CONTRIBUTING.md](../CONTRIBUTING.md).
