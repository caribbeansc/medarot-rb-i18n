# Cheats: Both Versions Bonus and Unlock Everything

Two small patches that make the game run its **own** unlock code. You never edit the
save file, and the game saves everything itself.

| Patch | What you get |
|---|---|
| **`both_versions_bonus`** | The official Both Versions Bonus: the other version's exclusive sleeves, wallpapers and player icons, plus the God Emperor and Fermion icons, which can't be obtained any other way. **Tickets are set to 999** (the game's maximum), so you can create the other version's exclusive cards in the Card Library without multiplayer. |
| **`unlock_everything`** | Everything above, **plus** the developers' own *Unlock All* routine from their debug menu: every card ×3, every medal (+10000 exp), every icon, wallpaper and sleeve (including the secret ones). It also marks the tutorial **and every story stage as cleared**, so only use it if that's what you want. |

Install **only one** of them. `unlock_everything` already includes the bonus.

## Works on a Switch and on emulators

Each patch comes in the two standard formats. Both work on a **real Switch with
Atmosphère** (custom firmware) and on **emulators**:

| Format | Switch (Atmosphère) | Eden, yuzu, Suyu, Sudachi, Citron | Ryujinx |
|---|:-:|:-:|:-:|
| **IPS** (exefs patch, applied when the game loads) | ✅ | ✅ | ✅ |
| **Cheat** (Atmosphère `dmnt` cheat, applied while the game runs) | ✅ | ✅ | ✅ |

The two formats write the same bytes; only the folder layout differs by platform.
Every folder holds the files for **all four releases** (Kuwagata and Kabuto, v1.0 and
v1.1). The game picks the one whose build ID matches, so you don't need to know
which release you have.

**Which one should I use?**

- **IPS** is the safest choice, especially on emulators: it's in place before any of
  the game's code runs. To turn it off, remove it or disable the mod.
- **Cheat** can be switched on and off from a cheat manager (EdiZon or Breeze on
  Switch; the emulator's cheat or add-on list).

Use one or the other, not both. Having both is harmless, but disabling the cheat
wouldn't turn off the IPS.

## Installing

Each patch folder (`both_versions_bonus/` or `unlock_everything/`) contains four
ready-made layouts:

| Folder | For |
|---|---|
| `switch-ips/` | Switch with Atmosphère, IPS |
| `switch-cheat/` | Switch with Atmosphère, cheat |
| `emulator-ips/` | Emulators, IPS |
| `emulator-cheat/` | Emulators, cheat |

### Switch (Atmosphère)

Copy the `atmosphere` folder from `switch-ips/` **or** `switch-cheat/` to the root of
your SD card, merging it with the existing one. Atmosphère enables cheats by default,
so once the cheat is copied it is active; you can turn it off with EdiZon or Breeze.

### Eden, yuzu, Suyu, Sudachi, Citron

Inside `emulator-ips/` (or `emulator-cheat/`) there is a folder per game, named by
title ID: `0100CB6024FF8000` is Kuwagata, `0100DE4023982000` is Kabuto. Copy the mod
folder it contains into the emulator's `load/<title id>/` folder. To find it,
right-click the game and choose **Open Mod Data Location**. Then enable the mod in the
game's **Properties → Add-Ons**. On Android, use the game's Add-ons screen to install
the folder.

### Ryujinx

Same folders, but the destination is `mods/contents/<title id>/`. Right-click the
game and choose **Open Mods Directory**. For the cheat, also tick it in
**Manage Cheats**.

## Using it

1. **Back up your save.**
2. Finish the tutorial first. The game only checks the bonus after the tutorial.
3. Install **one** patch, in **one** format, and start the game.
4. Go to the main menu (mode select). The **"Both Versions Bonus!"** dialog appears,
   and the game saves on its own afterwards.
5. Remove or disable the patch.

It fires once per game launch. While it stays installed it fires again on every
launch: tickets are refilled to 999, and `unlock_everything` runs again. That's
harmless, but you'll see the dialog every time.

## Why a patch and not the debug menu

The developers' debug launcher is still in the game's code: money, dust, tickets,
*Unlock All*, "other version save"… but its **scene was not shipped**. The retail build
contains only five scenes (logo, title, menu, battle, prologue), and no retail code
path loads the launcher, so it can't be opened on any platform. These patches call its
*Unlock All* routine directly instead.

## How it works

All the patches are in `Seq_Menu.ModeSelect.<CoCommonSetup>`, the code that grants the
Both Versions Bonus:

- The `isDualVersionBonusUnlocked` check is replaced by a once-per-launch latch. The
  latch uses `GlobalWork.debugOtherVersionSave`, a debug field the retail game never
  reads.
- `PrjSaveManager.IsExistSaveDataVersion(other version)` is replaced with `true`.
- Before `PlayerData.OpenVerion` runs, the patch sets the latch and `ticket = 999`.
- `unlock_everything` only: `CustomizeData.SetOwnOtherVersion` is replaced by the
  debug launcher's *Unlock All* routine, which never reads its arguments.

The new code lives in the body of an unused debug-launcher method. Each patch site
is found by method name, from an Il2CppDumper dump, and by instruction pattern, never by a
fixed offset; the result is checked by disassembly. [`REPORT.txt`](REPORT.txt) lists
every site and the resulting code for the four releases, and
[`tools/gen_cheats.py`](tools/gen_cheats.py) rebuilds everything from your own dumps.

**Status:** only verified statically, by disassembling the four releases. It hasn't
been run in the game yet. Reports are welcome.
