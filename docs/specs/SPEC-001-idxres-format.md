# SPEC-001 — `IdxRes2[2.0]` table format

The game keeps most of its data-driven text in 107 files under
`Data/StreamingAssets/IdxResData/IdxRes_*.bytes`. They are **loose files** in the
romfs, so LayeredFS can replace them without touching Unity bundles or the
Addressables catalog. Each file is one sheet of an Excel workbook serialized with
a custom format.

Reverse-engineered from the retail Switch dump; verified byte-exact against all
107 tables.

## Layout

All integers are little-endian. A *string* is `int32 byteLength` followed by that
many bytes of UTF-8, with **no** terminator and **no** padding.

```
str     magic          "IdxRes2[2.0]"
str     bytes_path     original path, e.g. "Assets/StreamingAssets/IdxResData/IdxRes_X.bytes"
str     xlsx_path      source workbook, e.g. "Assets/CnvData/IdxResData/IdxRes_X.xlsx"
str     sheet          sheet name inside the workbook
str     start_cell     top-left data cell, e.g. "B3"
uint32  col_count
col_count × {
    uint32  col_type
    str     col_name
}
uint32  row_count
row_count × {
    str     row_key    column A of the sheet; NOT unique
    uint32  sub_rows   a logical row may hold several sub-rows
    sub_rows × col_count cells, encoded per col_type
}
```

## Cell encodings

| `col_type` | Encoding | Python value |
|---:|---|---|
| 0 | raw `int32` (4 B) | `int` |
| 1 | raw `float32` (4 B) | `float` |
| 2 | raw `bool` (1 B) | `bool` |
| 3 | string (length-prefixed UTF-8) | `str` |
| 4 | `uint32 count` + count × `int32` | `list[int]` |
| 5 | `uint32 count` + count × `float32` | `list[float]` |
| 7 | `uint32 length` + length bytes | `{"hex": "rrggbbaa"}` |

Type 6 does not occur in the retail data and is rejected.

## Requirements

- **R-1** `parse()` rejects any buffer whose magic is not exactly `IdxRes2[2.0]`.
- **R-2** `parse()` rejects a buffer with trailing bytes after the last cell, and
  reports how many bytes were left over. A truncated buffer is also rejected.
- **R-3** `build(parse(data)) == data` for every retail table (byte-exact
  round-trip). This is the safety property the whole text pipeline rests on.
- **R-4** An unknown `col_type` raises `ValueError` on both read and write rather
  than being silently skipped.
- **R-5** Only `col_type == 3` cells are treated as translatable text.
- **R-6** `row_key` values may repeat; a parser must keep every row, in order,
  and must not deduplicate or reorder them.
- **R-7** `build()` rejects a row whose sub-row has a cell count different from
  `col_count`, naming the offending row key.
- **R-8** Non-ASCII text round-trips through the length prefix in **bytes**, not
  characters (a 3-byte kanji counts as 3).
- **R-9** A string cell may be empty (`length == 0`); that is distinct from a
  missing cell and must survive the round-trip.
