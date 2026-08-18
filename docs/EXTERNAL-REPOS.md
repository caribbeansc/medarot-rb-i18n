# External projects this repository stands on

This project is a thin layer over a handful of other people's work. This file
records exactly what each one gives us, how it reaches the user, and under which
licence, so the credit in the README has somewhere to point and so anyone
auditing the build can see what goes into it.

Nothing here bundles any part of the game. These are tools and libraries that
read *your own* dump on *your own* machine; see [NOTICE](../NOTICE).

## Bundled in the patcher executables

The double-clickable patcher ships these inside the `.exe` / `.app` so a player
needs nothing installed.

- **[UnityPy](https://github.com/K0lb3/UnityPy)** — K0lb3, MIT.
  Reads and rewrites the game's Unity assets: the 107 data tables, the scene
  files, the TextMeshPro components, the fonts, and the Switch textures. Every
  string and every texture this project patches passes through it. Its texture
  path also pulls in native helpers (`texture2ddecoder`, `etcpak`,
  `astc-encoder-py`) that decode/encode the console's ASTC textures; those are
  UnityPy's own dependencies and are credited through it.

- **[hactool](https://github.com/SciresM/hactool)** — SciresM, ISC.
  Decrypts and extracts the romfs from a Switch backup (`.xci` / `.nsp`),
  applying an update NCA over the base when present. The patcher fetches the
  Windows binary from hactool's releases and builds the macOS one from source
  (`.github/build-hactool.sh`), including an x86_64 cross-build for Intel Macs.

- **[nsz](https://github.com/nicoboss/nsz)** — nicoboss, MIT.
  Losslessly decompresses the compressed backup formats (`.nsz` / `.xcz`) back
  to `.nsp` / `.xci` before extraction, using zstd.

- **[Pillow](https://github.com/python-pillow/Pillow)** — the Pillow team,
  HPND (MIT-style). Composites the translated-texture deltas (overlay + mask)
  and handles every PNG the texture pipeline reads or writes.

- **[OpenSSL](https://www.openssl.org/)** — Apache-2.0.
  hactool links its `libcrypto` for the AES-XTS/CTR crypto that decrypts NCAs.
  On macOS the build links an OpenSSL bottle (an Intel one for the cross-build).

## Build tooling

- **[PyInstaller](https://github.com/pyinstaller/pyinstaller)** — the
  PyInstaller team, GPLv2 with a bootloader exception that lets the packaged
  apps carry any licence. Freezes `gui.py` and its dependencies into the
  standalone Windows and macOS executables in the release.

## Sibling project

- **[mdr-navi-i18n](https://github.com/caribbeansc/mdr-navi-i18n)** — the sister
  fan-translation project for the GBA *Medarot Navi* games. It shares this
  repository's approach — language packs that hold a key plus a fingerprint of
  the source string and the translation, never the game's own text — and the two
  keep their release scheme and README shape in sync.
