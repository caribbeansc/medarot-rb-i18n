# SPEC-005: Copyright-safe translation keys

The Japanese script of the game is the publisher's copyrighted work. This
repository must be redistributable, so **it stores no source text at all**: not
even as a comment. What it stores is a *reference* to a string plus the
translation of it.

Two kinds of reference exist.

### Positional (data tables)

An IdxRes cell is addressed by where it lives:

```json
{"row": "Ok", "sub": 0, "col": "text", "src": "8b1a7f22c0d4", "t": "Aceptar"}
```

`src` is a fingerprint of the original text, used only to detect that the game's
text changed under us (a patch, a different region). It is never used to
reconstruct anything.

### Content-addressed (bundles and scenes)

A label serialized in a prefab or a scene has no stable address: the same string
appears in dozens of objects: so it is addressed by the fingerprint itself:

```json
{"src": "3fa9c1e0b7d2", "t": "Turno {0}", "note": "battle HUD"}
```

At build time the tool hashes the Japanese string it finds in the user's own dump
and looks the translation up by that hash.

## Fingerprint

`src = sha256(text.encode("utf-8")).hexdigest()[:12]`

48 bits. It identifies a string the user already has; it does not carry it.

## Requirements

- **R-1** `fingerprint(text)` is the first 12 hex characters of the SHA-256 of
  the UTF-8 bytes, and is stable across runs, platforms and Python versions.
- **R-2** A fingerprint is not reversible and is not a compressed copy: it is
  fixed-length regardless of input length.
- **R-3** Writing a catalog fails loudly if two different source strings in the
  same catalog produce the same fingerprint (48-bit collision), naming both keys.
- **R-4** No file under `langs/` may contain a character in the ranges
  CJK punctuation (U+3000–U+303F), Hiragana (U+3040–U+309F), Katakana
  (U+30A0–U+30FF), CJK Unified Ideographs and extension A (U+3400–U+4DBF,
  U+4E00–U+9FFF), CJK compatibility ideographs (U+F900–U+FAFF), or halfwidth and
  fullwidth forms (U+FF00–U+FFEF). The last range is not optional: a cell whose
  entire content is `？` is still the game's text. This is a test, not a
  guideline.
- **R-5** A translation whose `src` no longer matches the game's current text is
  reported as **stale** and, by default, is **not** applied.
  `--allow-stale` applies it anyway.
- **R-6** Only strings that contain Japanese are ever extracted or replaced.
  Text the game already ships in English (`"New Record"`, `"MAX"`) is left
  untouched, because it coexisted with Japanese and will coexist with any other
  target language.
- **R-7** The work files under `work/`: the only place where source text and
  translation sit side by side: are excluded from version control by
  `.gitignore`, and `mrb sync` strips the source text when promoting them into
  `langs/`.
- **R-8** `mrb doctor` re-runs the R-4 check over the whole `langs/` tree so a
  contributor can verify their pack before opening a pull request.
- **R-9** A cell can hold different source text in different versions of the game:
  the v1.1 update rewrote fifteen of them, and two of those need a different
  translation. So the fingerprint is **part of the key**, not merely a check: a
  position may carry several entries, and the build applies the one whose
  fingerprint matches the text in the dump at hand. If none matches, nothing is
  applied (R-5).
- **R-10** Publishing keeps entries the current dump does not contain, so
  translating from one dump never deletes the work done against another. A pack
  can therefore support several versions of the game at once.
