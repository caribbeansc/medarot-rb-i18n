# How it works

Where the game keeps its text, and what this toolkit does about each place.

## The map

| Where | What is in it | How it is patched |
|---|---|---|
| `Data/StreamingAssets/IdxResData/*.bytes` | 3722 strings of data and UI: cards, skills, menus, tutorials, story lines | 107 tables in a custom format, rewritten byte-exact ([SPEC-001](specs/SPEC-001-idxres-format.md)) |
| `aa/Switch/*.bundle` (prefabs) | 2566 TextMeshPro labels baked into UI prefabs | typetree edit, addressed by `(bundle, path_id, field)` |
| `aa/Switch/*.bundle` (Texture2D) | UI artwork with text drawn into it | texture re-injection, original format preserved |
| `Data/level3`, `Data/sharedassets*.assets` | the battle scene's own text and textures | raw byte patching, because these have no usable typetree ([SPEC-002](specs/SPEC-002-unity-strings.md)) |
| `aa/Switch/font_assets_*.bundle` | the TextMeshPro fonts | fallback chain and kerning |
| every bundle with text components | letter spacing and glyph squeezing | one-off cache built by `mrb prepare` |

Those are not alternatives: a full translation needs all of them. Skip the scenes
and the battle screen stays Japanese. Skip the metrics and Latin letters overlap.

## The five things that were not obvious

**1. The data tables are loose files.** `IdxRes_*.bytes` sit in the romfs, not in
a Unity bundle, so LayeredFS can replace them without touching the Addressables
catalog. That is why a translation of the game's *text* needs no Unity surgery at
all — and why `mrb build --only tables` already produces something playable.

**2. Text is duplicated between bundles and scenes.** Many labels and textures
exist twice: once in a bundle under `aa/Switch/`, and once inside
`sharedassets*.assets`. The battle screens read the *scene* copy. Patch only the
bundle and nothing changes on screen. Both get patched, in that order.

**3. The scene MonoBehaviours have no typetree.** The script definitions are not
in the file, so their strings cannot be read as fields. They are found by locating
the Japanese bytes and walking *backwards* to a length prefix that fits exactly,
then rewritten in place with the padding restored. Conservative on purpose: a
candidate is rejected unless it decodes as strict UTF-8, its padding is zero, and
it holds no control characters.

**4. TextMeshPro was tuned for kana.** The components ship with
`m_characterSpacing` at -8 to -10 and `m_charWidthMaxAdj` at 30-50%. With kana
(~36 px wide) that reads fine. With Latin letters (~10-18 px) the glyphs overlap
and strokes vanish: "Bullet" rendered as "Bulet", "Wild" as "W'd". Zeroing both
makes TMP shrink text that does not fit instead of crushing it. This is
language-independent, so `mrb prepare` does it once into `work/<title id>/base/`
and every language build reuses it.

**5. UnityPy corrupts 30 of this game's textures.** It decides a Switch texture is
swizzled with `gobs_per_block > 1`, but that value is the height of the block in
GOBs and Unity picks 1 for short textures. Those textures are read *and rewritten*
as linear data: scrambled blocks and a magenta band. The fix is one comparison,
applied before any Unity file is opened — see
[SPEC-009](specs/SPEC-009-switch-textures.md). The failure is invisible when
extracting and only shows up on screen, which is why a test scans the source to
make sure no module can bypass it.

## A note on rebuilt textures

Textures are stored as ASTC 5x5, which is lossy. Re-injecting a texture without
changing a single pixel already shifts some of them: about 1% of the pixels move,
by up to 22 per channel. On a texture where you replaced a block of text, the
error concentrates on the high-contrast edges of the new letters and peaks around
40-60.

That is the codec, not the pipeline. Two builds of the same translation will not
produce byte-identical bundles, and comparing bundles byte-for-byte is not a
useful test — comparing the decoded pixels, with a tolerance, is.

## Versions of the game

Four dumps are known to work: Kuwagata Ver. and Kabuto Ver., each with and without
the v1.1 update.

The two releases carry **identical data tables**. In fact, without the update
their romfs is byte-identical except for four files (`boot.config`,
`globalgamemanagers`, `resources.assets` and IL2CPP's `global-metadata.dat`) — the
difference between Kuwagata and Kabuto arrives with the update, which swaps eight
bundles of background and gacha art. So a translation of the text applies to any
of them.

The update also adds one table (the crowdfunding backers), rewrites fifteen cells
of text and adds nine more; twelve of those fifteen are a model number that lost a
hyphen.

Since names, sizes and table contents are identical across releases, the only
thing that identifies a dump is Unity's `build-guid` in `Data/boot.config`. That is
what `setup` reads to pick the title id, and what tells a prepared cache from one
dump apart from another.

That is why the fingerprint of the source string is part of the translation key
(SPEC-005/R-9): a cell can carry two entries, one per wording, and the build
applies the one that matches the dump in front of it. Nothing is guessed: a line
with no matching entry is left in the original language and reported.

## The flow

```
your dump (romfs)
      │
      │  mrb extract          reads tables, bundles and scenes
      ▼
work/                         source text + inventories (never committed)
      │
      │  you translate        terminal, spreadsheet or editor
      ▼
work/lang/<code>/             original next to translation
      │
      │  mrb sync <code>      drops the source text
      ▼
langs/<code>/                 keys + fingerprints + translations (committed)
      │
      │  mrb build <code>     + your dump, + the prepared cache
      ▼
build/<code>/<Mod>/romfs/     the LayeredFS mod
      │
      │  mrb install <code>
      ▼
your emulator
```

The split in the middle is the whole design: the half that is publishable holds no
game data, and the half that holds game data never leaves your machine
([SPEC-005](specs/SPEC-005-translation-keys.md)).

## Build steps, in order

Order is load-bearing. A step that touches a file an earlier step wrote starts
from the *written* copy, so no step can undo another.

1. `tables` — the 107 data tables
2. `fonts` — fallback chain, kerning
3. `bundle-labels` — TMP labels in prefabs
4. `bundle-textures` — artwork in bundles
5. `scene-labels` — text inside `level*` / `*.assets`
6. `scene-textures` — artwork inside `level*` / `*.assets`
7. `sprite-atlas` — artwork as packed into sprite atlases

`mrb build <lang> --only tables,fonts` or `--skip sprite-atlas` if you are
iterating on one thing. Every patched file is re-opened and read back before the
build is called a success.

## What ends up in the mod

```
build/es/MedarotRB_ES/romfs/Data/
├── StreamingAssets/IdxResData/IdxRes_*.bytes
├── StreamingAssets/aa/Switch/*.bundle
├── level3
└── sharedassets0.assets, sharedassets3.assets, …
```

Only files that actually changed. The emulator overlays them on top of the final
romfs (base + update), which is exactly what you extracted.
