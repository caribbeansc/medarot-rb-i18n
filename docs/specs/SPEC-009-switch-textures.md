# SPEC-009 — Switch block-linear textures

UnityPy ≤ 1.25.3 mis-detects whether a Switch texture is swizzled:

```python
# UnityPy/helpers/TextureSwizzler.py
def is_switch_swizzled(platform, platform_blob) -> bool:
    ...
    return get_switch_gobs_per_block(platform_blob) > 1      # should be >= 1
```

`gobs_per_block = 1 << platform_blob[8:12]` is the **height of the block in
GOBs**, not a flag. Unity picks 1 for short textures, and the Tegra X1
block-linear layout still interleaves inside the GOB (64×8 bytes, zig-zag) and
still pads the width to 4 blocks. So with `gobs == 1` the data is read as linear:
scrambled blocks and a magenta band.

30 textures in this game are affected. The same gate guards the **write** path,
so without the fix a re-injected texture is written linear and the console reads
garbage.

## Requirements

- **R-1** `apply_fix()` replaces the predicate with `>= 1` and is idempotent: it
  may be called any number of times, from any module.
- **R-2** `apply_fix()` must run before the first `UnityPy.load()`, and patches
  both `UnityPy.helpers.TextureSwizzler` and the reference held by
  `UnityPy.export.Texture2DConverter`.
- **R-3** `apply_fix()` is a no-op for non-Switch platforms and for a
  `platform_blob` shorter than 12 bytes.
- **R-4** Texture format id 49 is `ASTC_RGB_5x5`, not `ASTC_RGBA_4x4` (48).
  Re-injection must pass the original format explicitly or the ASTC size
  computation fails with `Invalid ASTC data size`.
- **R-5** `is_affected(obj, data)` reports whether a given texture triggers the
  bug, so `mrb doctor --textures` can audit a dump.
- **R-6** Every module in this project that imports UnityPy calls `apply_fix()`
  at import time. A test asserts this by scanning the source tree, because the
  failure is invisible when extracting and only shows up on screen.
