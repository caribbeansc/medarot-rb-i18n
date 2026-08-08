# SPEC-004 — Language pack layout

A language is a directory. Adding one must not require touching a single line of
Python.

```
langs/<code>/
├── lang.json              metadata + behaviour switches (schema below)
├── idxres/<Table>.json    translations for the IdxRes data tables
├── labels.json            translations for text serialized in bundles/scenes
├── textures/<Name>.json   render specs for baked-in text
├── textures/delta/        generated overlays + masks (see SPEC-003)
└── GLOSSARY.md            optional, human-facing terminology rules
```

`<code>` is a BCP-47-ish lowercase tag: `es`, `en`, `pt-br`, `fr`.

## `lang.json`

```json
{
  "code": "es",
  "name": "Español",
  "english_name": "Spanish",
  "mod_name": "MedarotRB_ES",
  "font": {
    "fallbacks": ["FOT-CezannePro-DB SDF", "LiberationSans SDF"],
    "global_fallbacks": true,
    "neutralize_kerning": true,
    "fix_tmp_metrics": true
  },
  "validation": {
    "extra_chars": "áéíóúÁÉÍÓÚñÑüÜ¡¿«»—–…·♪",
    "max_line": 46,
    "length_factor": 1.25
  },
  "ascii_fallback": { "á": "a", "ñ": "n", "¡": "", "¿": "" },
  "credits": ["..."]
}
```

## Requirements

- **R-1** `discover()` lists every directory under `langs/` that contains a
  readable `lang.json`, sorted by code; nothing else is scanned.
- **R-2** `code`, `name` and `mod_name` are mandatory. A pack missing any of them
  fails to load with a message naming the file and the missing field.
- **R-3** `code` must match `^[a-z]{2,3}(-[a-z0-9]{2,8})*$`; `mod_name` must be a
  single path segment with no separators, so it cannot escape the mods directory.
- **R-4** Every other field is optional and has a documented default:
  no font fallbacks, kerning **not** neutralized, TMP metrics **fixed**, no extra
  characters allowed, `max_line = 46`, `length_factor = 1.25`, no ASCII fallback.
- **R-5** Unknown keys in `lang.json` are preserved on write and ignored on read,
  so a newer pack stays loadable by an older checkout.
- **R-6** `font.fallbacks` names TextMeshPro font assets **by name**, never by
  PathID, so a pack keeps working on a different dump of the game.
- **R-7** A language pack contains no Japanese source text (enforced by
  SPEC-005/R-4 and by `tests/test_packs.py`).
- **R-8** Two packs may translate the same key differently; packs never read each
  other's files.
