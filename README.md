# Ship Graveyard Simulator - Level.sav crash workaround
Unofficial community workaround, **currently confirmed on one save** for:

```text
LowLevelFatalError [File:Unknown] [Line: 2908]
BP_Computer_C /Game/ShipGraveyard/Maps/GameMap1.GameMap1:PersistentLevel.BP_Computer_GEN_VARIABLE_BP_Computer_C_CAT_248 was found in memory and is an export but does not have all load flags.
```

## Requirements
- Windows and Python 3 (`py` or `python` command); no third-party Python packages
- The game must be **closed**

## Automatic usage (no renaming needed)

1. Close the game. Temporarily disable Steam Cloud synchronization to prevent a cloud save from overwriting your repair.
2. **Make a separate copy of the whole save folder**, ideally outside the game's directories.
3. Unzip this tool anywhere and double-click **`Fix_Level_Save.bat`**.
4. It searches `%LOCALAPPDATA%\ShipGraveyard\Saved\SaveGames` for `Level.sav`. If there is more than one slot, choose the **affected** save from the numbered menu. You may also put the tool in the same folder as `Level.sav` and run it there.
5. After all validation succeeds, it creates **`Level.bak`** (exact, unmodified original) next to **`Level.sav`**, then safely replaces **`Level.sav`** with the repaired file.
6. Load the affected save and test it. Keep `Level.bak` until you have confirmed everything is working. Re-enable Steam Cloud only after resolving any synchronization conflicts in favor of the repaired save.

**Do not run the fix repeatedly.** If `Level.bak` already exists the tool refuses to run, rather than risking your previous backup. If the target record is not found or the structure is unsupported, it makes no changes.

## Manually specify a location (optional)

You can drag `Level.sav` onto `Fix_Level_Save.bat`, or run:

```powershell
py ship_graveyard_save_fix.py "C:\path\to\SGSGame1\Level.sav"
```

Or run the Python script without an argument for auto-discovery:

```powershell
py ship_graveyard_save_fix.py
```

To experiment with a different error mentioning `CAT_123`:

```powershell
py ship_graveyard_save_fix.py "C:\path\to\SGSGame1\Level.sav" --cat 123
```

**Only CAT_248 has been confirmed to work in-game.** Don't guess a CAT number.

## Safety and technical details

- Validates the game's zlib block headers and compressed data
- Verifies record layout, actor count, record boundary, and file length
- Removes the obfuscated `BP_Computer_GEN_VARIABLE_BP_Computer_C_CAT_248` actor record and updates decoded length and actor count
- Recompresses and verifies the result *before changing files*
- Writes a verified temporary file in the same directory; then creates `Level.bak` with exclusive-create semantics, and verifies backup bytes
- Atomically replaces `Level.sav` on the same filesystem after backup succeeds
- Never overwrites an existing `Level.bak`, never edits `Player.sav`

In the confirmed case it removed 3,255 decoded bytes and changed the actor count from 543 to 542. The affected actor's saved state may be lost. This is not guaranteed to solve other crashes.

## Restore the backup

Close the game, temporarily disable Steam Cloud, and copy `Level.bak` back over `Level.sav` in the same save-slot folder (leave `Level.bak` intact). Your original game state will be restored.

## Troubleshooting

- **Multiple slots:** select the slot that crashes; don't assume it's slot 1.
- **`Level.bak` already exists:** tool refuses to overwrite your backup; do not delete it without securing another copy first.
- **`Expected exactly one ... found 0`:** the referenced record is not in this save; the fix does not apply.
- **Invalid layout or zlib error:** unsupported/corrupt format; original is left unchanged.
- **Python missing:** install Python 3 and retry.

This is an independent community workaround, not an official game patch. Feedback from other users would help establish how widely it works.
