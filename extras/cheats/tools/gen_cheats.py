#!/usr/bin/env python3
"""Build the "Both Versions Bonus" and "Unlock Everything" patches.

For every build it finds the patch sites by method name (from Il2CppDumper's
``script.json``) and by instruction pattern, never by a fixed offset, and checks
the result by disassembling it. It writes each patch twice, as a cheat (Atmosphère
``dmnt`` format) and as an IPS exefs patch, laid out for a Switch SD card and for
emulators.

    pip install capstone lz4
    python gen_cheats.py --out .. \\
        --dump "Kuwagata v1.1" 0100CB6024FF8000 <exefs>/main <il2cppdumper>/script.json \\
        --dump "Kuwagata v1.0" 0100CB6024FF8000 ... \\
        --dump "Kabuto v1.1"   0100DE4023982000 ... \\
        --dump "Kabuto v1.0"   0100DE4023982000 ...

The exefs comes from your own dump (``hactool --exefsdir``), and ``script.json``
from running Il2CppDumper on that ``main`` plus the dump's
``romfs/Data/Managed/Metadata/global-metadata.dat``.

How the patch works. Everything happens in ``Seq_Menu.ModeSelect.<CoCommonSetup>``,
the code that grants the Both Versions Bonus. That code already shows a dialog and
saves the game when it finishes:

  P1  ldrb w8,[x0,#0x30]   (isDualVersionBonusUnlocked)  -> bl GATE
      GATE returns w8 = GlobalWork.inst.debugOtherVersionSave. That is a debug bool
      the retail game never reads; we use it as a once-per-launch latch.
  P2  bl PrjSaveManager.IsExistSaveDataVersion           -> mov w0,#1
      (pretend the other version's save exists)
  P3  bl PlayerData.OpenVerion                           -> bl TICKETS
      TICKETS sets the latch, sets ticket = 999 and tail-calls OpenVerion.
  P4  (Unlock Everything only)
      bl CustomizeData.SetOwnOtherVersion                -> bl <Unlock All>._OnPressed
      That is the developers' own "unlock all" routine, from their debug launcher.

GATE and TICKETS live in the body of the debug launcher's "other version save" item
(its _GetTextJA method). The launcher's scene is not shipped, so nothing in the
retail game can reach that code.
"""
from __future__ import annotations

import argparse
import bisect
import json
import shutil
import struct
from pathlib import Path

import capstone
import lz4.block

TICKETS_VALUE = 999  # GameDef.TICKET_MAX

# Debug launcher items, by class name (Seq_Launcher namespace).
UNLOCK_ALL = "Seq_Launcher.\u5168\u958b\u653e$$_OnPressed"              # "Unlock All"
OTHER_VERSION_SAVE = "Seq_Launcher.\u5225\u30d0\u30fc\u30b8\u30e7\u30f3\u30bb\u30fc\u30d6$$_GetTextJA"  # "Other version save"

VARIANTS = {
    "both_versions_bonus": ("Medarot RB - Both Versions Bonus", False),
    "unlock_everything": ("Medarot RB - Unlock Everything", True),
}

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)


# ─── NSO and IPS ──────────────────────────────────────────────────────────────

NSO_HEADER = 0x100  # IPS offsets address the NSO including this header


class Nso:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        if raw[:4] != b"NSO0":
            raise SystemExit(f"{path}: not an NSO0")
        self.build_id = raw[0x40:0x50].hex().upper()
        segments = []
        for i in range(3):
            file_off, mem_off, size = struct.unpack_from("<III", raw, 0x10 + i * 16)
            csize = struct.unpack_from("<I", raw, 0x60 + i * 4)[0]
            blob = raw[file_off:file_off + csize]
            flags = struct.unpack_from("<I", raw, 0x0C)[0]
            data = lz4.block.decompress(blob, uncompressed_size=size) if flags & (1 << i) else blob
            segments.append((mem_off, data))
        if segments[0][0] != 0:
            raise SystemExit(f"{path}: .text does not start at 0")
        self.text_end = len(segments[0][1])
        end = segments[2][0] + len(segments[2][1])
        img = bytearray(end)
        for off, data in segments:
            img[off:off + len(data)] = data
        self.img = bytes(img)


def build_ips(words: list[tuple[int, int]]) -> bytes:
    out = bytearray(b"IPS32")
    for addr, word in sorted(words):
        out += struct.pack(">IH", addr + NSO_HEADER, 4) + struct.pack("<I", word)
    return bytes(out + b"EEOF")


# ─── Encoding ─────────────────────────────────────────────────────────────────

def _rel(pc, t, bits):
    off = (t - pc) // 4
    assert -(1 << (bits - 1)) <= off < (1 << (bits - 1)), (hex(pc), hex(t))
    return off & ((1 << bits) - 1)


def enc_b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def enc_bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def enc_ret(): return 0xD65F03C0
def enc_movz_w(rd, imm): return 0x52800000 | (imm << 5) | rd
def enc_ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def enc_str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt
def enc_ldrb(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt
def enc_strb(rt, rn, off): return 0x39000000 | (off << 10) | (rn << 5) | rt
def enc_cbz_x(rt, pc, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def enc_str_x_pre(rt, rn, imm): return 0xF8000C00 | ((imm & 0x1FF) << 12) | (rn << 5) | rt
def enc_ldr_x_post(rt, rn, imm): return 0xF8400400 | ((imm & 0x1FF) << 12) | (rn << 5) | rt


def enc_adrp(pc, rd, target):
    imm = (((target & ~0xFFF) - (pc & ~0xFFF)) >> 12) & 0x1FFFFF
    return 0x90000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | rd


# ─── Analysis ─────────────────────────────────────────────────────────────────

class Build:
    def __init__(self, name, tid, main, script):
        self.name, self.tid = name, tid.upper()
        self.nso = Nso(Path(main))
        self.img = self.nso.img
        d = json.loads(Path(script).read_text(encoding="utf-8"))
        m = sorted((x["Address"], x["Name"]) for x in d["ScriptMethod"])
        self.meth = [a for a, _ in m]
        self.names = [n for _, n in m]
        self.meta = {x["Address"]: x["Name"] for x in d["ScriptMetadata"]}

    def u64(self, a): return struct.unpack_from("<Q", self.img, a)[0]

    def method(self, pred):
        hits = {a for a, n in zip(self.meth, self.names) if pred(n)}
        assert len(hits) == 1, f"{self.name}: {len(hits)} candidates"
        return hits.pop()

    def end_of(self, addr):
        return self.meth[bisect.bisect_right(self.meth, addr)]


def analyse(b: Build) -> dict:
    ends = lambda s: (lambda n: n.endswith(s))
    get_system = b.method(ends("gs.SaveData$$get_system"))
    exist = b.method(ends("gs.PrjSaveManager$$IsExistSaveDataVersion"))
    open_ver = b.method(ends("gs.SaveData.PlayerData$$OpenVerion"))
    set_other = b.method(ends("gs.SaveData.CustomizeData$$SetOwnOtherVersion"))
    unlock_all = b.method(ends(UNLOCK_ALL))
    cave = b.method(ends(OTHER_VERSION_SAVE))
    setup = b.method(lambda n: "Seq_Menu.ModeSelect.<CoCommonSetup>" in n and n.endswith("$$MoveNext"))

    code = list(md.disasm(b.img[setup:b.end_of(setup)], setup))
    found = dict(site_flag=None, site_exist=None, site_open=None, site_setown=None, gw_slot=None)
    regs = {}
    for i, ins in enumerate(code):
        t = int(ins.op_str.lstrip("#"), 16) if ins.mnemonic == "bl" else None
        if t == get_system and code[i + 1].op_str == "w8, [x0, #0x30]" and code[i + 1].mnemonic == "ldrb":
            assert code[i + 2].mnemonic == "cbnz" and code[i + 2].op_str.startswith("w8,")
            assert found["site_flag"] is None
            found["site_flag"] = code[i + 1].address
        for key, target in (("site_exist", exist), ("site_open", open_ver), ("site_setown", set_other)):
            if t == target:
                assert found[key] is None, key
                found[key] = ins.address
        if ins.mnemonic == "adrp":
            regs[ins.op_str.split(",")[0]] = int(ins.op_str.split("#")[1], 16)
        elif ins.mnemonic == "ldr" and "#" in ins.op_str:
            rd, rest = ins.op_str.split(", ", 1)
            base = rest.strip("[").split(",")[0]
            if base in regs and rd == base:
                slot = regs[base] + int(rest.split("#")[1].rstrip("]"), 16)
                if b.meta.get(b.u64(slot)) == "gs.GlobalWork_TypeInfo":
                    assert found["gw_slot"] in (None, slot)
                    found["gw_slot"] = slot
    missing = [k for k, v in found.items() if v is None]
    assert not missing, f"{b.name}: not found: {missing}"
    check_unused(b, cave)
    check_ignores_args(b, unlock_all)
    return dict(found, setup=setup, open_ver=open_ver, unlock_all=unlock_all,
                cave=cave, cave_end=b.end_of(cave))


def check_unused(b: Build, addr: int) -> None:
    """Nothing may branch straight into the method whose body we reuse."""
    import array
    words = array.array("I")
    words.frombytes(b.img[:b.nso.text_end])
    for i, w in enumerate(words):
        if (w >> 26) in (0b100101, 0b000101):
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            assert i * 4 + imm * 4 != addr, f"{b.name}: direct call to {addr:#x} from {i*4:#x}"
    aliases = [n for a, n in zip(b.meth, b.names) if a == addr]
    assert len(aliases) == 1, f"{b.name}: {aliases}"


def check_ignores_args(b: Build, addr: int) -> None:
    """Unlock All is called with arguments it never expected: it must not read them."""
    md_detail = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    md_detail.detail = True
    written = set()
    for ins in md_detail.disasm(b.img[addr:b.end_of(addr)], addr):
        read, write = ins.regs_access()
        for r in (ins.reg_name(x) for x in read):
            if r in ("x0", "w0", "x1", "w1"):
                assert "x" + r[1:] in written, f"{b.name}: Unlock All reads {r} at {ins.address:#x}"
        written |= {"x" + n[1:] for n in (ins.reg_name(x) for x in write) if n[0] in "xw"}


# ─── Building ─────────────────────────────────────────────────────────────────

def build_words(info: dict, unlock_all: bool) -> list[tuple[int, int]]:
    """Cave code first, then the branches into it (the cheat VM writes in order)."""
    words = []

    def load_inst(pc):
        # x9 = GlobalWork.inst, with null checks patched to jump to `fail` later
        seq = [enc_adrp(pc, 9, info["gw_slot"]),
               enc_ldr_x(9, 9, info["gw_slot"] & 0xFFF),
               enc_ldr_x(9, 9, 0),        # Il2CppClass*
               "cbz",
               enc_ldr_x(9, 9, 0xB8),     # static fields
               enc_ldr_x(9, 9, 0),        # GlobalWork.inst
               "cbz"]
        return seq

    def place(start, seq, fail):
        for i, w in enumerate(seq):
            pc = start + 4 * i
            words.append((pc, enc_cbz_x(9, pc, fail) if w == "cbz" else w))
        return start + 4 * len(seq)

    gate = info["cave"]
    body = [enc_str_x_pre(9, 31, -16)] + load_inst(gate + 4) + [
        enc_ldrb(8, 9, 0x7C),            # w8 = latch (0: grant, 1: skip)
        enc_ldr_x_post(9, 31, 16),
        enc_ret()]
    gate_fail = gate + 4 * len(body)
    body += [enc_movz_w(8, 1), enc_ldr_x_post(9, 31, 16), enc_ret()]
    gate_end = place(gate, body, gate_fail)

    tickets = (gate_end + 0xF) & ~0xF
    body = load_inst(tickets) + [enc_movz_w(8, 1), enc_strb(8, 9, 0x7C)]
    tickets_set = tickets + 4 * len(body)
    body += [enc_movz_w(8, TICKETS_VALUE), enc_str_w(8, 0, 0x20)]   # PlayerData.ticket
    body.append(enc_b(tickets + 4 * len(body), info["open_ver"]))
    tickets_end = place(tickets, body, tickets_set)
    assert tickets_end <= info["cave_end"], "cave too small"

    words.append((info["site_flag"], enc_bl(info["site_flag"], gate)))
    words.append((info["site_exist"], enc_movz_w(0, 1)))
    words.append((info["site_open"], enc_bl(info["site_open"], tickets)))
    if unlock_all:
        words.append((info["site_setown"], enc_bl(info["site_setown"], info["unlock_all"])))
    info.update(gate=gate, tickets=tickets, tickets_end=tickets_end)
    return words


def listing(b: Build, info: dict, words) -> list[str]:
    img = bytearray(b.img)
    for a, w in words:
        struct.pack_into("<I", img, a, w)
        assert list(md.disasm(struct.pack("<I", w), a)), f"{a:#x}: {w:08x} does not disassemble"
    out = []

    def show(a, n, title):
        out.append(f"  {title}")
        out.extend(f"    {i.address:08x}  {i.mnemonic:6} {i.op_str}" for i in md.disasm(bytes(img[a:a + 4 * n]), a))

    show(info["gate"], (info["tickets"] - info["gate"]) // 4, "GATE")
    show(info["tickets"], (info["tickets_end"] - info["tickets"]) // 4, "TICKETS")
    for k in ("site_flag", "site_exist", "site_open", "site_setown"):
        show(info[k] - 4, 3, k)
    return out


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data) if isinstance(data, bytes) else path.write_text(data, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dump", nargs=4, action="append", required=True,
                    metavar=("NAME", "TITLE_ID", "MAIN", "SCRIPT_JSON"))
    args = ap.parse_args()

    for variant in VARIANTS:
        shutil.rmtree(args.out / variant, ignore_errors=True)
    report = []
    for name, tid, main_path, script in args.dump:
        b = Build(name, tid, main_path, script)
        info = analyse(b)
        bid, bid16 = b.nso.build_id, b.nso.build_id[:16]
        report.append(f"== {name}  ({b.tid}, build ID {bid})")
        report += [f"  {k:12} {info[k]:#x}" for k in
                   ("setup", "site_flag", "site_exist", "site_open", "site_setown", "gw_slot",
                    "open_ver", "unlock_all", "cave", "cave_end")]
        for variant, (mod, unlock) in VARIANTS.items():
            words = build_words(info, unlock)
            report.append(f" [{variant}]")
            report += listing(b, info, words)
            cheat = f"[{mod} ({name})]\n" + "".join(f"04000000 {a:08X} {w:08X}\n" for a, w in words)
            ips = build_ips(words)
            v = args.out / variant
            write(v / "switch-cheat" / "atmosphere" / "contents" / b.tid / "cheats" / f"{bid16}.txt", cheat)
            write(v / "switch-ips" / "atmosphere" / "exefs_patches" / f"medarot_{variant}" / f"{bid}.ips", ips)
            write(v / "emulator-cheat" / b.tid / f"{mod} (cheat)" / "cheats" / f"{bid16}.txt", cheat)
            write(v / "emulator-ips" / b.tid / f"{mod} (IPS)" / "exefs" / f"{bid}.ips", ips)
    write(args.out / "REPORT.txt", "\n".join(report) + "\n")
    print("\n".join(line for line in report if line.startswith("==")))


if __name__ == "__main__":
    main()
