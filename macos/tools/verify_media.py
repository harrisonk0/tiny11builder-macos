#!/usr/bin/env python3
"""Validate ISO boot structures and mounted-media content without a VM."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import stat
import struct
import subprocess


def require_resident(path):
    if getattr(path.stat(), 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0x40000000):
        raise RuntimeError(f'{path.name} is offloaded. In Finder choose Download Now/Keep Downloaded first.')


def digest(path):
    require_resident(path)
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            sha.update(block)
    return sha.hexdigest()


def boot_catalog(iso):
    with iso.open('rb') as stream:
        catalog = None
        for sector in range(16, 256):
            stream.seek(sector * 2048)
            record = stream.read(2048)
            if record[0:1] == b'\0' and record[1:6] == b'CD001' and b'EL TORITO SPECIFICATION' in record[7:39]:
                catalog = struct.unpack_from('<I', record, 71)[0]
                break
        if catalog is None:
            raise RuntimeError('No El Torito boot record')
        stream.seek(catalog * 2048)
        data = stream.read(2048)
    if data[30:32] != b'\x55\xaa' or sum(struct.unpack('<16H', data[:32])) % 65536:
        raise RuntimeError('Invalid El Torito validation checksum/signature')
    entries = []
    def entry(offset, platform):
        item = data[offset:offset + 32]
        if item[0] != 0x88 or item[1] != 0:
            raise RuntimeError('Expected bootable, no-emulation entry')
        entries.append({'platform': platform, 'load_sectors': struct.unpack_from('<H', item, 6)[0],
                        'image_lba': struct.unpack_from('<I', item, 8)[0]})
    entry(32, data[1])
    offset = 64
    while data[offset] in (0x90, 0x91):
        final, platform, count = data[offset] == 0x91, data[offset + 1], struct.unpack_from('<H', data, offset + 2)[0]
        offset += 32
        for _ in range(count):
            entry(offset, platform)
            offset += 32
        if final:
            break
    if {item['platform'] for item in entries} != {0, 239}:
        raise RuntimeError('Expected BIOS and EFI platform entries')
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('iso', type=Path)
    parser.add_argument('--tree', type=Path, required=True, help='Original prepared setup tree')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    require_resident(args.iso)
    for relative in ('sources/install.wim', 'sources/boot.wim', 'boot/etfsboot.com',
                     'efi/microsoft/boot/efisys.bin', 'efi/boot/bootx64.efi'):
        candidate = args.tree / relative
        if candidate.is_file():
            require_resident(candidate)
    entries = boot_catalog(args.iso)
    paths = {0: 'boot/etfsboot.com', 239: 'efi/microsoft/boot/efisys.bin'}
    with args.iso.open('rb') as stream:
        for entry in entries:
            expected = (args.tree / paths[entry['platform']]).read_bytes()
            stream.seek(entry['image_lba'] * 2048)
            if stream.read(len(expected)) != expected:
                raise RuntimeError('ISO boot payload differs from prepared Microsoft boot image')
    attached = subprocess.check_output(['hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', str(args.iso)])
    entities = plistlib.loads(attached)['system-entities']
    mount = next(Path(entity['mount-point']) for entity in entities if 'mount-point' in entity)
    checks = {}
    try:
        for name in ('sources/install.wim', 'sources/boot.wim', 'autounattend.xml', 'efi/boot/bootx64.efi'):
            expected, actual = args.tree / name, mount / name
            sha = digest(actual)
            if sha != digest(expected):
                raise RuntimeError(f'Mounted ISO content differs: {name}')
            checks[name] = {'bytes': actual.stat().st_size, 'sha256': sha, 'matches_staging': True}
        binary = (mount / 'efi/boot/bootx64.efi').read_bytes()
        pe = struct.unpack_from('<I', binary, 60)[0]
        if binary[:2] != b'MZ' or binary[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', binary, pe + 4)[0] != 0x8664:
            raise RuntimeError('EFI loader is not a valid x64 PE image')
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount)], check=True)
    report = {'iso_sha256': digest(args.iso), 'catalog': entries, 'boot_payloads_match_staging': True,
              'mounted_media': checks, 'x64_efi_loader': True, 'firmware_boot_verified': False,
              'windows_installation_verified': False, 'windows_servicing_verified': False}
    args.report.write_text(json.dumps(report, indent=2))
    print('ISO structures and mounted-file content validated. Firmware/Windows execution remains unverified.')


if __name__ == '__main__':
    main()
