# SPEC-006: Build pipeline and mod layout

`mrb build <lang>` turns a language pack plus the user's own romfs into a
LayeredFS mod.

## Output layout

```
build/<code>/<mod_name>/romfs/Data/
├── StreamingAssets/IdxResData/IdxRes_*.bytes          translated data tables
├── StreamingAssets/aa/Switch/*.bundle                 labels, textures, fonts, metrics
├── level0 … level4                                    scene text/textures
└── sharedassets*.assets, resources.assets             scene text/textures
```

Only files that actually changed are written. LayeredFS overlays them on top of
the final romfs (base + update), which is exactly what was extracted.

## Steps, in order

| # | Step | Reads | Writes |
|--:|------|-------|--------|
| 1 | `tables` | `idxres/*.json` | `IdxRes_*.bytes` |
| 2 | `fonts` | `lang.json` | `font_assets_*.bundle` |
| 3 | `bundle-labels` | `labels.json` + inventory | UI bundles |
| 4 | `bundle-textures` | `textures/delta/` | UI bundles |
| 5 | `scene-labels` | `labels.json` | `level*`, `*.assets` |
| 6 | `scene-textures` | `textures/delta/` | `level*`, `*.assets` |
| 7 | `sprite-atlas` | `textures/delta/` | `level*`, `*.assets` |

## Requirements

- **R-1** Order matters and is fixed: a step that touches a file already written
  by an earlier step must start from the **written** copy, never from the romfs,
  so no step can undo another.
- **R-2** A build starts from a clean output directory unless `--keep` is passed.
  Two consecutive builds of the same inputs produce the same set of files.
- **R-3** Every step is skippable (`--only`, `--skip`) and reports what it did:
  files touched, strings applied, strings skipped.
- **R-4** TMP metric fixes are language-independent and expensive (they touch
  every bundle), so they are produced once by `mrb prepare` into a cache under
  `work/<title id>/base/` and reused by every language build. A build without that cache
  still succeeds, and warns that Latin text will look cramped.
  The cache is **part of the mod**, not merely something to read from: a bundle
  that only needed the metric fix is not rewritten by any other step, so every
  cached file the build did not otherwise produce is copied into the mod. Leaving
  them out silently ships cramped text for those screens.
- **R-5** After patching, each written bundle is re-opened and the patched values
  are read back; a mismatch fails the build instead of shipping a broken bundle.
- **R-6** Textures are re-injected with the texture's **original** format
  (`target_format=d.m_TextureFormat`). Letting the library choose breaks ASTC
  5x5 (see SPEC-009/R-4).
- **R-7** A translation whose target no longer exists in the dump (missing row,
  missing column, unknown label) is reported and skipped; it never aborts the
  build. The same goes for a cell whose text this dump spells differently and for
  which the pack has no matching entry (SPEC-005/R-9): reported, left in the
  original language, never guessed at.
- **R-8** `mrb install <lang>` copies `romfs/` into every detected emulator, and
  supports `--to <dir>` for anything not auto-detected. It never deletes anything
  outside `<mods dir>/<mod_name>/`.
- **R-9** Emulator detection covers Windows, macOS and Linux, both the
  Ryujinx-style `mods/contents/<lowercase title id>/` and the yuzu-style
  `load/<UPPERCASE TITLE ID>/` layouts.
- **R-10** `--ascii` applies the pack's `ascii_fallback` map to every string
  before writing, for players whose font patch did not take.

## Packaging

The same build feeds the two layouts Switch modding uses. They are both LayeredFS;
only the path differs.

| Format | Layout | Read by |
|---|---|---|
| `emulator` | `<mod name>/romfs/Data/…` | Ryujinx, Ryubing, yuzu, sudachi, Eden, Citron, Suyu |
| `atmosphere` | `atmosphere/contents/<UPPERCASE TITLE ID>/romfs/Data/…` | Atmosphère CFW on real hardware |

- **R-11** `mrb package <lang>` stages both layouts under `dist/<lang>/<format>/`
  from the **same** build output, so the two can never drift apart. The romfs tree
  inside each is byte-identical.
- **R-12** Atmosphère uses the uppercase title id and has no room for a mod name;
  the emulator layout uses a named directory. Neither layout is nested inside the
  other.
- **R-13** `--zip` produces an archive whose paths are relative to the layout root,
  so unpacking it at the root of an SD card (Atmosphère) or of a mods directory
  (emulator) puts every file where it belongs.
- **R-14** `mrb install <lang> --sd <path>` writes the Atmosphère layout onto a
  mounted card, replacing only `atmosphere/contents/<title id>/romfs`. It refuses
  a path that is not a directory rather than creating one.
- **R-15** The title id is configuration, not a constant: `mrb setup --title-id`
  stores it and every install and packaging path derives from it. The game has a
  sister release (Kabuto Ver.) which is a different title with identical file
  formats, so the tools must be able to target it. A value that is not 16 hex
  digits is rejected.
- **R-16** `mrb setup` identifies the dump itself and sets the title id
  accordingly, so the user does not have to know it. The identifier is Unity's
  `build-guid` in `Data/boot.config`, which is unique per build and therefore
  distinguishes all four known dumps: Kuwagata Ver. and Kabuto Ver., each with and
  without the v1.1 update. Nothing coarser works: **without the update the two
  releases ship a byte-identical romfs except for four files**, with the same
  names, sizes and table contents throughout. An unrecognised build keeps the
  configured title id and says so rather than guessing.
- **R-17** Everything derived from a dump lives under `work/<title id>/`, so two
  dumps on one machine cannot mix inventories or caches, and `MEDAROT_ROMFS` /
  `MEDAROT_TITLE_ID` override the stored configuration for a single command.
