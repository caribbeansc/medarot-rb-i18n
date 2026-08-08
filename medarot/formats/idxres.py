"""Reader/writer for the game's ``IdxRes2[2.0]`` data tables.

See ``docs/specs/SPEC-001-idxres-format.md`` for the format and the guarantees
this module must uphold. The important one is SPEC-001/R-3: ``build(parse(x))``
is byte-identical to ``x`` for every retail table, which is what makes it safe to
rewrite these files at all.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = "IdxRes2[2.0]"

TYPE_INT = 0
TYPE_FLOAT = 1
TYPE_BOOL = 2
TYPE_STRING = 3
TYPE_INT_ARRAY = 4
TYPE_FLOAT_ARRAY = 5
TYPE_BLOB = 7

TYPE_NAMES = {
    TYPE_INT: "int",
    TYPE_FLOAT: "float",
    TYPE_BOOL: "bool",
    TYPE_STRING: "string",
    TYPE_INT_ARRAY: "int[]",
    TYPE_FLOAT_ARRAY: "float[]",
    TYPE_BLOB: "blob",
}


@dataclass
class Column:
    type: int
    name: str


@dataclass
class Row:
    key: str
    #: ``cells[sub_row][column]`` -> int | float | bool | str | list | {"hex": ...}
    cells: list = field(default_factory=list)


@dataclass
class Table:
    bytes_path: str
    xlsx_path: str
    sheet: str
    start_cell: str
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)

    def column_index(self, name: str) -> int:
        for i, column in enumerate(self.columns):
            if column.name == name:
                return i
        raise KeyError(name)

    def string_columns(self) -> list[tuple[int, str]]:
        """Indices and names of the translatable columns (SPEC-001/R-5)."""
        return [(i, c.name) for i, c in enumerate(self.columns) if c.type == TYPE_STRING]


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def u32(self) -> int:
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def i32(self) -> int:
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def f32(self) -> float:
        value = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return value

    def blob(self) -> bytes:
        size = self.u32()
        if size > len(self.data) - self.pos:
            raise ValueError(
                f"truncated blob at offset {self.pos - 4}: asked for {size} bytes, "
                f"{len(self.data) - self.pos} left"
            )
        out = self.data[self.pos:self.pos + size]
        self.pos += size
        return out

    def string(self) -> str:
        return self.blob().decode("utf-8")

    def cell(self, col_type: int):
        if col_type == TYPE_INT:
            return self.i32()
        if col_type == TYPE_FLOAT:
            return self.f32()
        if col_type == TYPE_BOOL:
            value = self.data[self.pos]
            self.pos += 1
            return bool(value)
        if col_type == TYPE_STRING:
            return self.string()
        if col_type == TYPE_INT_ARRAY:
            return [self.i32() for _ in range(self.u32())]
        if col_type == TYPE_FLOAT_ARRAY:
            return [self.f32() for _ in range(self.u32())]
        if col_type == TYPE_BLOB:
            return {"hex": self.blob().hex()}
        raise ValueError(f"unknown column type: {col_type}")


def _write_string(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    out += struct.pack("<I", len(raw)) + raw


def _write_cell(out: bytearray, value, col_type: int) -> None:
    if col_type == TYPE_INT:
        out += struct.pack("<i", value)
    elif col_type == TYPE_FLOAT:
        out += struct.pack("<f", value)
    elif col_type == TYPE_BOOL:
        out += bytes([1 if value else 0])
    elif col_type == TYPE_STRING:
        _write_string(out, value)
    elif col_type == TYPE_INT_ARRAY:
        out += struct.pack("<I", len(value))
        for item in value:
            out += struct.pack("<i", item)
    elif col_type == TYPE_FLOAT_ARRAY:
        out += struct.pack("<I", len(value))
        for item in value:
            out += struct.pack("<f", item)
    elif col_type == TYPE_BLOB:
        raw = bytes.fromhex(value["hex"]) if isinstance(value, dict) else bytes(value)
        out += struct.pack("<I", len(raw)) + raw
    else:
        raise ValueError(f"unknown column type: {col_type}")


def parse(data: bytes) -> Table:
    """Parse a table. Raises ``ValueError`` on anything unexpected."""
    reader = _Reader(data)
    try:
        magic = reader.string()
    except (struct.error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"not an IdxRes table: {exc}") from exc
    if magic != MAGIC:
        raise ValueError(f"unexpected magic: {magic!r} (expected {MAGIC!r})")

    table = Table(
        bytes_path=reader.string(),
        xlsx_path=reader.string(),
        sheet=reader.string(),
        start_cell=reader.string(),
    )
    for _ in range(reader.u32()):
        col_type = reader.u32()
        col_name = reader.string()
        if col_type not in TYPE_NAMES:
            raise ValueError(f"unknown column type {col_type} for column {col_name!r}")
        table.columns.append(Column(col_type, col_name))

    for _ in range(reader.u32()):
        row = Row(key=reader.string())
        for _ in range(reader.u32()):
            row.cells.append([reader.cell(c.type) for c in table.columns])
        table.rows.append(row)

    if reader.pos != len(data):
        raise ValueError(f"{len(data) - reader.pos} bytes left unparsed")
    return table


def parse_file(path) -> Table:
    with open(path, "rb") as handle:
        return parse(handle.read())


def build(table: Table) -> bytes:
    """Serialize a table back to bytes."""
    out = bytearray()
    _write_string(out, MAGIC)
    _write_string(out, table.bytes_path)
    _write_string(out, table.xlsx_path)
    _write_string(out, table.sheet)
    _write_string(out, table.start_cell)

    out += struct.pack("<I", len(table.columns))
    for column in table.columns:
        out += struct.pack("<I", column.type)
        _write_string(out, column.name)

    out += struct.pack("<I", len(table.rows))
    for row in table.rows:
        _write_string(out, row.key)
        out += struct.pack("<I", len(row.cells))
        for sub in row.cells:
            if len(sub) != len(table.columns):
                raise ValueError(
                    f"row {row.key!r}: {len(sub)} cells but {len(table.columns)} columns"
                )
            for value, column in zip(sub, table.columns):
                _write_cell(out, value, column.type)
    return bytes(out)


def roundtrip_ok(path) -> bool:
    with open(path, "rb") as handle:
        data = handle.read()
    return build(parse(data)) == data


def table_name(path) -> str:
    """``…/IdxRes_Text_Menu.bytes`` -> ``Text_Menu``."""
    from pathlib import Path

    return Path(path).stem.replace("IdxRes_", "", 1)
