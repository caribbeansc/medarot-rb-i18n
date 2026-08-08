# SPEC-002: Unity serialized strings (raw patching)

Some screens: the battle scene above all: do not read their labels from
bundles but from the scene files themselves (`Data/level*`,
`Data/sharedassets*.assets`). Those `MonoBehaviour`s carry no usable typetree
(the script definitions are not in the file), so their strings must be found and
replaced **in the raw object bytes**.

A string inside a serialized Unity object is:

```
int32 length | length bytes of UTF-8 | zero padding up to a multiple of 4
```

## Requirements

- **R-1** `find_jp_strings(raw)` returns `(offset_of_the_int32, text)` pairs,
  sorted by offset, for every string that contains Japanese (kana or CJK
  ideographs).
- **R-2** A candidate is accepted only if **all** of these hold:
  strict UTF-8 decode; `2 <= length <= 8192`; the whole string fits in the
  buffer; the padding bytes are zero; no control characters other than
  `\n`, `\r`, `\t`.
- **R-3** The scan starts from the Japanese bytes and walks *backwards* looking
  for a length prefix that fits exactly, so it does not depend on the alignment
  of the object inside the file.
- **R-4** Overlapping matches are impossible: once a string is accepted, no
  other match may start inside it.
- **R-5** `replace_strings(raw, [(offset, old, new)])` verifies both the stored
  length and the stored bytes at `offset` before writing, and raises otherwise.
  It never writes a "best effort" patch.
- **R-6** Replacement re-encodes the new length in bytes and re-pads to a
  multiple of 4; the rest of the buffer is copied verbatim.
- **R-7** Replacing a string with itself yields a byte-identical buffer.
- **R-8** ASCII-only strings are ignored by the scan: the tool only ever
  translates Japanese source text (see SPEC-005/R-6).
