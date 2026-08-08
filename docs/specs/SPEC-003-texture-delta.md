# SPEC-003 — Texture translation delta

Some text is baked into textures (prologue cards, button art, tutorial art).
Shipping the translated texture would mean shipping the game's artwork, so this
repository stores **only the difference** the translation introduces:

```
langs/<code>/textures/delta/<Name>.png        RGBA overlay: final value of every changed pixel
langs/<code>/textures/delta/<Name>.mask.png   L mask: 255 where a pixel changed
```

The mask is required because a pixel can change *to* transparent (erasing
Japanese text that sits on an alpha background), which the overlay alone cannot
distinguish from "unchanged".

Patchers rebuild the final texture as *original from the user's own dump* + delta,
so the repository never contains the artwork.

This toolkit does not draw text: you export the texture, edit the PNG in whatever
image editor you like, and import it back. Only the diff is kept.

## Requirements

- **R-1** `make_diff(original, translated)` returns `(overlay, mask, percent)`
  where `overlay` is RGBA of the same size, transparent outside the mask.
- **R-2** A pixel counts as changed if any of R, G, B or A differs — **except**
  that two fully transparent pixels are equal regardless of their RGB. Without
  this, the delta of a texture with an alpha background would be the whole image.
- **R-3** `apply_diff(original, *make_diff(original, translated)[:2])` reproduces
  `translated` exactly, including the alpha channel.
- **R-4** If the translation changed nothing, the mask is empty and `percent` is
  `0.0`.
- **R-5** The mask filename is the overlay filename with `.png` replaced by
  `.mask.png`.
- **R-6** If an overlay has no mask beside it, it is treated as a complete
  replacement image (legacy format), not as a delta.
- **R-7** A delta produced at one size is resized to the target texture's size
  before being applied, never cropped.
- **R-8** Importing an edited PNG diffs it against the texture in the **user's own
  dump**, resizing the import if its size differs, and refuses an image that is
  identical to the original (there would be nothing to store).
- **R-9** A language pack may ship `textures/textures.json`, a plain list of
  `{"texture", "text"}` saying what each translated texture is supposed to read.
  It is documentation for reviewers; no build step depends on it.
- **R-10** Importing reports which edges of the texture the edit runs into **that
  the original did not use**. Translated text is routinely wider than the Japanese
  it replaces and the game clips it silently, so this is the only warning a
  translator gets. The comparison against the original matters: many textures
  legitimately paint to the border, and flagging those would drown the real cases.
