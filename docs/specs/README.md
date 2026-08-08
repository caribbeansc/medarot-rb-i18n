# Specifications

This project is developed **spec-first**: every non-obvious behaviour is written
down as a numbered requirement *before* it is implemented, and every requirement
has at least one test that references its ID.

| Spec | Title | Tests |
|------|-------|-------|
| [SPEC-001](SPEC-001-idxres-format.md) | `IdxRes2[2.0]` table format | `tests/test_idxres.py`, `tests/test_extract.py` |
| [SPEC-002](SPEC-002-unity-strings.md) | Unity serialized strings (raw patching) | `tests/test_unitystr.py` |
| [SPEC-003](SPEC-003-texture-delta.md) | Texture translation delta | `tests/test_texdiff.py`, `tests/test_textures.py` |
| [SPEC-004](SPEC-004-language-pack.md) | Language pack layout | `tests/test_lang.py`, `tests/test_packs.py` |
| [SPEC-005](SPEC-005-translation-keys.md) | Copyright-safe translation keys | `tests/test_catalog.py`, `tests/test_workspace.py`, `tests/test_packs.py` |
| [SPEC-006](SPEC-006-build-pipeline.md) | Build pipeline, mod layout and packaging | `tests/test_build.py`, `tests/test_install.py`, `tests/test_package.py`, `tests/test_build_real.py` |
| [SPEC-007](SPEC-007-cli.md) | Command-line interface | `tests/test_cli.py` |
| [SPEC-008](SPEC-008-validator.md) | Translation validator | `tests/test_validate.py` |
| [SPEC-009](SPEC-009-switch-textures.md) | Switch block-linear textures | `tests/test_switchtex.py` |

## How to read a requirement ID

`SPEC-001/R-3` means "requirement 3 of spec 1". Tests name the requirements they
cover in their docstring, so `pytest -k R-3` and `grep -r "SPEC-001/R-3"` both
work.

## Rules for changing a spec

1. Change the spec text first, in its own commit.
2. Update or add the tests that reference the changed requirement.
3. Only then change the implementation.

A requirement with no test is a bug in the spec.
