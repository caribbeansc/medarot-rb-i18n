# SPEC-008 — Translation validator

`mrb validate <lang>` catches the mistakes that would otherwise be found by
playing the game for an hour.

## Checks

| Check | Level | Rule |
|-------|-------|------|
| leftover source text | error | no Japanese characters in a translation |
| placeholders | error | the multiset of `{0}`, `{1}`, … matches the original |
| markup | error | the multiset of TMP tags (`<color=…>`, `</size>`, `<nobr>`, …) matches |
| charset | error | every character is ASCII, in `validation.extra_chars`, or one of the whitespace controls the game itself uses (`\n`, `\r`, `\t`) |
| stale key | error | `src` no longer matches the game's text (SPEC-005/R-5) |
| length budget | warning | Latin text longer than `length_factor × 2 ×` the CJK length |
| line width | warning | a line longer than `validation.max_line` when the original had line breaks |
| empty | info | key present but not translated yet |

## Requirements

- **R-1** Errors set exit code 1; warnings alone set exit code 0.
- **R-2** Every finding names the language, the file, the key and the offending
  value, in that order, on a single line, so the output is greppable.
- **R-3** Checks that need the original text (placeholders, markup, length,
  stale) require an extracted `work/` and are **skipped with a notice**, not
  silently, when it is absent. Checks that do not (charset, leftover source text)
  always run.
- **R-4** The charset check ignores the contents of TMP tags: `<color=#AABBCC>`
  must not be reported for `#`.
- **R-5** A CJK character in the original counts as 2 Latin characters for the
  length budget; the budget is `max(length_factor × 2 × cjk_len, cjk_len + 12)`
  so that very short strings are not flagged.
- **R-6** `--strict` promotes every warning to an error.
- **R-7** The validator never writes to disk.
