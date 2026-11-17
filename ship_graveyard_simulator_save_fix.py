#!/usr/bin/env python3
"""Remove the confirmed crash-causing BP_Computer CAT record from a Ship Graveyard Simulator Level.sav.

Standard-library only. Tested with the user's crashing save and the repaired save.
Creates Level.bak, then safely replaces Level.sav in place after validation.
"""
import argparse
import os
import shutil
import tempfile
import struct
import sys
import zlib
from pathlib import Path

MAGIC = bytes.fromhex('c1 83 2a 9e 00 00 00 00')
HEADER_SIZE = 48
CHUNK_SIZE = 131072


class SaveError(Exception):
    pass


def unpack_save(raw):
    result = bytearray()
    pos = 0
    count = 0
    while pos < len(raw):
        if len(raw) - pos < HEADER_SIZE or raw[pos:pos + 8] != MAGIC:
            raise SaveError(f'Invalid compression header at file offset 0x{pos:X}')
        chunk_size, compressed, uncompressed, compressed2, uncompressed2 = struct.unpack_from('<5Q', raw, pos + 8)
        if (chunk_size != CHUNK_SIZE or compressed != compressed2 or
                uncompressed != uncompressed2 or not 0 < uncompressed <= CHUNK_SIZE or
                compressed == 0 or pos + HEADER_SIZE + compressed > len(raw)):
            raise SaveError(f'Unexpected block size/header at 0x{pos:X}')
        data = raw[pos + HEADER_SIZE:pos + HEADER_SIZE + compressed]
        try:
            obj = zlib.decompressobj()
            block = obj.decompress(data)
            block += obj.flush()
        except zlib.error as e:
            raise SaveError(f'Zlib decompression failed at 0x{pos:X}: {e}') from e
        if not obj.eof or obj.unused_data or obj.unconsumed_tail or len(block) != uncompressed:
            raise SaveError(f'Invalid or truncated zlib block at 0x{pos:X}')
        result.extend(block)
        pos += HEADER_SIZE + compressed
        count += 1
    if not count:
        raise SaveError('Empty input file')
    return bytes(result)


def pack_save(data):
    output = bytearray()
    for pos in range(0, len(data), CHUNK_SIZE):
        block = data[pos:pos + CHUNK_SIZE]
        compressed = zlib.compress(block, level=6)
        output += MAGIC
        output += struct.pack('<5Q', CHUNK_SIZE, len(compressed), len(block),
                              len(compressed), len(block))
        output += compressed
    return bytes(output)


def locate_record(data, cat):
    # Actor names in this game are stored byte-by-byte with each byte reduced by one.
    actor = f'BP_Computer_GEN_VARIABLE_BP_Computer_C_CAT_{cat}'
    actor_bytes = bytes((c - 1) & 0xff for c in actor.encode('ascii'))
    # A leading int32 gives the length, without a null terminator for this actor type.
    signature = struct.pack('<I', len(actor_bytes)) + actor_bytes
    found = []
    start = 0
    while True:
        idx = data.find(signature, start)
        if idx < 0:
            break
        start = idx + 1
        found.append(idx)
    if len(found) != 1:
        raise SaveError(f'Expected exactly one {actor} record, found {len(found)}. No changes made.')

    offset = found[0]
    after_name = offset + len(signature)
    # Verified layout for this particular actor in the supplied save:
    # 40 bytes of actor transform/metadata, 1 flag, uint32 property length,
    # property bytes, followed by eight zero bytes.
    if after_name + 45 > len(data):
        raise SaveError('Actor metadata is truncated')
    prop_len = struct.unpack_from('<I', data, after_name + 41)[0]
    end_of_properties = after_name + 45 + prop_len
    end_of_record = end_of_properties + 8
    if not (0 < prop_len < len(data) and end_of_record <= len(data)):
        raise SaveError('Actor property length is invalid')
    if data[end_of_properties:end_of_record] != b'\x00' * 8:
        raise SaveError('Actor record does not have the expected 8-byte terminator')
    if b'ShipBooked\x00' not in data[after_name + 45:end_of_properties]:
        raise SaveError('Unexpected BP_Computer properties; unsupported save layout')
    # Ensure the following bytes resemble the start of the next actor record.
    if end_of_record < len(data):
        if len(data) - end_of_record < 8:
            raise SaveError('Truncated data after record')
        next_len = struct.unpack_from('<I', data, end_of_record)[0]
        if not 0 < next_len < 1024 or end_of_record + 4 + next_len > len(data):
            raise SaveError('Record boundary is not followed by a valid actor name')
        next_name = data[end_of_record + 4:end_of_record + 4 + next_len]
        if not all(31 <= x <= 126 for x in next_name):
            raise SaveError('Record boundary validation failed')
    return actor, offset, end_of_record


def patch(data, cat):
    if len(data) < 12:
        raise SaveError('Save header too short')
    declared_len, actor_count = struct.unpack_from('<II', data, 0)
    if declared_len != len(data) - 4:
        raise SaveError('Save length field does not match actual data')
    if actor_count < 1 or actor_count > 1000000:
        raise SaveError('Actor count is invalid')
    actor, start, end = locate_record(data, cat)
    fixed = bytearray(data[:start] + data[end:])
    struct.pack_into('<I', fixed, 0, len(fixed) - 4)
    struct.pack_into('<I', fixed, 4, actor_count - 1)
    assert len(fixed) == len(data) - (end - start)
    if struct.unpack_from('<II', fixed, 0) != (len(fixed) - 4, actor_count - 1):
        raise SaveError('Internal validation failed')
    return bytes(fixed), actor, start, end, actor_count


def discover_saves():
    """Prefer a local Level.sav, otherwise search installed game save slots."""
    for folder in (Path.cwd(), Path(__file__).resolve().parent):
        candidate = folder / 'Level.sav'
        if candidate.is_file():
            return [candidate]

    localappdata = os.environ.get('LOCALAPPDATA')
    if not localappdata:
        return []
    save_root = Path(localappdata) / 'ShipGraveyard' / 'Saved' / 'SaveGames'
    if not save_root.is_dir():
        return []
    # Discover normal slot folders and a Level.sav directly in SaveGames.
    return sorted((p for p in save_root.glob('**/Level.sav') if p.is_file()),
                  key=lambda p: str(p).lower())


def select_save(explicit):
    if explicit is not None:
        return explicit / 'Level.sav' if explicit.is_dir() else explicit
    candidates = discover_saves()
    if not candidates:
        raise SaveError('Level.sav not found automatically. Put this tool in the save slot '
                        'folder or pass the path to Level.sav as an argument.')
    if len(candidates) == 1:
        return candidates[0]
    print('Multiple save slots found. Select the affected Level.sav:')
    for number, candidate in enumerate(candidates, 1):
        print(f'  {number}. {candidate}')
    try:
        selection = input('Slot number (Enter to cancel): ').strip()
    except EOFError as exc:
        raise SaveError('No interactive input available; pass the file path instead.') from exc
    if not selection.isdecimal() or not 1 <= int(selection) <= len(candidates):
        raise SaveError('Canceled: no valid save slot selected.')
    return candidates[int(selection) - 1]


def safe_repair(save, cat):
    save = save.resolve()
    if not save.is_file() or save.name.lower() != 'level.sav':
        raise SaveError(f'Expected an existing Level.sav, got: {save}')
    backup = save.with_name('Level.bak')
    if backup.exists():
        raise SaveError(f'Backup already exists: {backup}. Refusing to overwrite it. '
                        'Move it to a safe location before retrying.')

    original = save.read_bytes()
    decoded = unpack_save(original)
    fixed, actor, start, end, old_count = patch(decoded, cat)
    packed = pack_save(fixed)
    if unpack_save(packed) != fixed:
        raise SaveError('Compressed output failed round-trip verification')
    # Validate again through the same record finder: the targeted actor must be gone.
    if locate_count(fixed, cat) != 0:
        raise SaveError('Target actor still present after patch')

    # Stage output next to original so os.replace is atomic on the same filesystem.
    fd, staged = tempfile.mkstemp(prefix='.Level_fix_', suffix='.tmp', dir=save.parent)
    staged = Path(staged)
    backup_created = False
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(packed)
            handle.flush()
            os.fsync(handle.fileno())
        if unpack_save(staged.read_bytes()) != fixed:
            raise SaveError('Staged output verification failed')
        # Exclusive creation guarantees we do not overwrite an older backup.
        with backup.open('xb') as handle:
            backup_created = True
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        if backup.read_bytes() != original:
            raise SaveError('Backup verification failed; original left unchanged')
        # Guard against concurrent modification before replacement.
        if save.read_bytes() != original:
            raise SaveError('Level.sav changed while repairing; original left unchanged')
        os.replace(staged, save)
    finally:
        if staged.exists():
            staged.unlink()
    print(f'SUCCESS: removed {actor}')
    print(f'Actor count: {old_count} -> {old_count - 1}; removed {end-start} decoded bytes')
    print(f'Active save: {save}')
    print(f'Unmodified backup: {backup}')
    print('Load the affected slot to confirm the repair. Keep Level.bak safe.')


def locate_count(data, cat):
    actor = f'BP_Computer_GEN_VARIABLE_BP_Computer_C_CAT_{cat}'
    encoded = bytes((c - 1) & 0xff for c in actor.encode('ascii'))
    return data.count(struct.pack('<I', len(encoded)) + encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('save', nargs='?', type=Path,
                        help='Optional Level.sav or its folder (otherwise detected automatically)')
    parser.add_argument('--cat', type=int, default=248,
                        help='Computer CAT ID shown in the crash (default: 248)')
    args = parser.parse_args()
    if not 0 <= args.cat <= 999999:
        parser.error('--cat must be between 0 and 999999')
    try:
        save = select_save(args.save)
        print(f'Target: {save}')
        safe_repair(save, args.cat)
    except (SaveError, OSError, struct.error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
