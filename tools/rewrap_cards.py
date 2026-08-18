"""Re-break CardDef skill texts so every line fits the card detail panels.

The card detail panels do not word-wrap reliably: they auto-size, so a text
without manual ``\\n`` breaks gets squeezed into one line that spills past the
panel, and a manual line wider than the panel either gets crammed or re-wraps
leaving orphan words. Lines therefore have to be broken by hand, and every
line has to fit the narrowest panel on its own.

The width model below is proportional (an average Latin glyph = 1 unit) and
was calibrated against 12 in-game screenshots: lines up to 35.3 units fit the
narrowest panel, lines of 36.1 units already wrapped. BUDGET stays at 35.

Line-count limits come from the JP designer's own spec, found in the
placeholder text of the panel component (``TextInfo_00/01`` in
``menu_assets_all``): skill1 + skill2 may use 6 lines in total, a lone block 8.

Usage::

    python3 tools/rewrap_cards.py es          # dry run: report only
    python3 tools/rewrap_cards.py es --write  # re-break and save
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = 35.0
MAX_PAIR_LINES = 6
MAX_SINGLE_LINES = 8

NARROW = set("iljí!.,':;|¡")
SEMI = set("ftr()[]\"1 ")
WIDE = set("mwMW")
CAPS = set("ABCDEFGHIJKLMNOPQRSTUVXYZÁÉÍÓÚÑ")


def char_w(ch):
    if ch in NARROW:
        return 0.45
    if ch in SEMI:
        return 0.6
    if ch in WIDE:
        return 1.5
    if ch in CAPS:
        return 1.2
    return 1.0


def width(s):
    return sum(char_w(c) for c in s)


def tokenize(text):
    """Words; ``[ ... ]`` keyword groups stay atomic."""
    raw = text.split(" ")
    out, buf = [], []
    for tok in raw:
        if buf:
            buf.append(tok)
            if "]" in tok:
                out.append(" ".join(buf))
                buf = []
        elif tok.startswith("[") and "]" not in tok:
            buf = [tok]
        else:
            out.append(tok)
    if buf:
        out.append(" ".join(buf))
    return [t for t in out if t]


def wrap(text, budget=BUDGET):
    """Minimum-raggedness wrap: fewest lines first, then balanced."""
    # Some legacy cells carry literal "\n"/"\r" sequences (backslash + letter);
    # the game turns them into breaks at runtime, so flatten them like real ones.
    flat = " ".join(text.replace("\\n", " ").replace("\\r", " ").split())
    words = tokenize(flat)
    n = len(words)
    if n == 0:
        return text
    ws = [width(w) for w in words]
    space = char_w(" ")

    INF = float("inf")
    LINE_COST = 200.0
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        line_w = 0.0
        for i in range(j - 1, -1, -1):
            line_w += ws[i] + (space if line_w else 0.0)
            if line_w > budget and i < j - 1:
                break
            # a single word over budget is allowed (reported by the caller)
            cost = LINE_COST + (0.0 if j == n else (budget - line_w) ** 2)
            if best[i] + cost < best[j]:
                best[j] = best[i] + cost
                back[j] = i
    lines, j = [], n
    while j > 0:
        i = back[j]
        lines.append(" ".join(words[i:j]))
        j = i
    lines.reverse()
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        sys.exit("usage: rewrap_cards.py <lang> [--write]")
    warnings = []
    for lang in args:
        path = ROOT / "langs" / lang / "idxres" / "CardDef.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = {}
        changed = 0
        for e in doc["entries"]:
            if "skillText" not in e["col"] or not e.get("t"):
                continue
            new = wrap(e["t"])
            if new != e["t"]:
                changed += 1
                e["t"] = new
            rows.setdefault((e["row"], e["sub"]), {})[e["col"]] = new.count("\n") + 1
            for line in new.split("\n"):
                if width(line) > BUDGET:
                    warnings.append(f"{lang} {e['row']}.{e['col']}: line of "
                                    f"{width(line):.1f} units: {line!r}")
        for (row, sub), cols in sorted(rows.items()):
            total = sum(cols.values())
            if len(cols) >= 2 and total > MAX_PAIR_LINES:
                warnings.append(f"{lang} {row} (sub {sub}): {cols} = {total} lines "
                                f"(max {MAX_PAIR_LINES} for the pair) — shorten the text")
            elif len(cols) == 1 and total > MAX_SINGLE_LINES:
                warnings.append(f"{lang} {row} (sub {sub}): {total} lines "
                                f"(max {MAX_SINGLE_LINES}) — shorten the text")
        print(f"{lang}: {changed} cells re-broken" + ("" if write else " (dry run)"))
        if write:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    if warnings:
        print("\nNeeds manual attention:")
        for w in warnings:
            print(" -", w)
        sys.exit(1)


if __name__ == "__main__":
    main()
