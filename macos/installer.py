"""Native image customization with explicit deferred target servicing."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import stat
import xml.etree.ElementTree as ET

from config import load, HIVES
from hives import Hive

ROOT = Path(__file__).resolve().parent


def command(args, *, capture=False, input=None, preserve=False):
    env = dict(os.environ)
    env['WIMLIB_IMAGEX_IGNORE_CASE'] = '1'
    env.pop('TINY11_PRESERVE_METADATA', None)
    if preserve:
        env['TINY11_PRESERVE_METADATA'] = '1'
    values = [str(x) for x in args]
    if Path(values[0]).name in ('wimlib-imagex', 'mkisofs') and shutil.which('taskpolicy'):
        values = ['taskpolicy', '-b', 'nice', '-n', '19', *values]
    result = subprocess.run(values, text=True, input=input, env=env,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args[0]}\n{result.stderr or ''}")
    return result.stdout


def quoted(path):
    text = str(path)
    if any(c in text for c in ('"', '\n', '\r')):
        raise RuntimeError(f'Unsupported path in WIM command: {path}')
    return '"' + text + '"'


def rewrite_hives(wim, image, operations, scratch, tool):
    scratch.mkdir(parents=True)
    hive_names = sorted({op['hive'] for op in operations})
    metadata_before = {name: command([tool, 'dir', wim, str(image),
                                      '--path=/' + HIVES[name], '--detailed'], capture=True)
                      .split('Unnamed data stream:')[0] for name in hive_names}
    command([tool, 'extract', wim, str(image), *[HIVES[name] for name in hive_names],
             '--preserve-dir-structure', '--dest-dir=' + str(scratch)])
    replacements, results = [], []
    for name in hive_names:
        original = scratch / HIVES[name]
        if not original.is_file():
            raise RuntimeError(f'Expected hive absent from image {image}: {HIVES[name]}')
        edited = original.with_name(original.name + '.edited')
        relevant = [op for op in operations if op['hive'] == name]
        with Hive(original, write=True) as hive:
            for op in relevant:
                if op['action'] == 'set':
                    hive.set(op['key'], op['name'], op['type'], op['value'])
                else:
                    hive.delete(op['key'])
            hive.commit(edited)
        # Check final state, allowing earlier settings to be deleted by later operations.
        with Hive(edited) as hive:
            for op in relevant:
                if op['action'] == 'set':
                    deleted_later = any(later['action'] == 'delete' and
                                        (op['key'].lower() == later['key'].lower() or
                                         op['key'].lower().startswith(later['key'].lower() + '\\'))
                                        for later in relevant[relevant.index(op) + 1:])
                    if not deleted_later and hive.read(op['key'], op['name']) != Hive.encode(op['type'], op['value']):
                        raise RuntimeError(f'Hive validation failed: {name} {op}')
                elif hive.node(op['key']):
                    raise RuntimeError(f'Deleted hive key remains: {name} {op}')
        results.append({'hive': name, 'operations': len(relevant), 'verified_after_commit': True})
        replacements.append(f'add {quoted(edited)} {quoted("/" + HIVES[name])}')
    command([tool, 'update', wim, str(image)], input='\n'.join(replacements) + '\n', preserve=True)
    for name in hive_names:
        after = command([tool, 'dir', wim, str(image), '--path=/' + HIVES[name], '--detailed'], capture=True)
        if after.split('Unnamed data stream:')[0] != metadata_before[name]:
            raise RuntimeError(f'Windows metadata changed for hive {name}; refusing to package the image')
    # Re-extract and compare actual stored hive bytes, not just the temporary files.
    readback = scratch / 'readback'
    readback.mkdir()
    command([tool, 'extract', wim, str(image), *[HIVES[name] for name in hive_names],
             '--preserve-dir-structure', '--dest-dir=' + str(readback)])
    for name in hive_names:
        edited = (scratch / HIVES[name]).with_name(Path(HIVES[name]).name + '.edited')
        actual = readback / HIVES[name]
        if hashlib.sha256(edited.read_bytes()).digest() != hashlib.sha256(actual.read_bytes()).digest():
            raise RuntimeError(f'WIM hive read-back failed: {name}')
    for result in results:
        result['windows_metadata_preserved'] = True
    return results


def answer_file(path):
    namespace = 'urn:schemas-microsoft-com:unattend'
    wcm = 'http://schemas.microsoft.com/WMIConfig/2002/State'
    ET.register_namespace('', namespace)
    ET.register_namespace('wcm', wcm)
    def add(parent, tag, value=None, **attributes):
        element = ET.SubElement(parent, '{' + namespace + '}' + tag, attributes)
        element.text = value
        return element
    root = ET.Element('{' + namespace + '}unattend')
    def component(pass_name, name):
        settings = add(root, 'settings', **{'pass': pass_name})
        return add(settings, 'component', name=name, processorArchitecture='amd64',
                   publicKeyToken='31bf3856ad364e35', language='neutral', versionScope='nonSxS')
    setup = component('windowsPE', 'Microsoft-Windows-Setup')
    dynamic = add(setup, 'DynamicUpdate')
    add(dynamic, 'WillShowUI', 'OnError')
    image = add(add(setup, 'ImageInstall'), 'OSImage')
    add(image, 'Compact', 'true')
    add(image, 'WillShowUI', 'OnError')
    metadata = add(add(image, 'InstallFrom'), 'MetaData', **{'{' + wcm + '}action': 'add'})
    add(metadata, 'Key', '/IMAGE/INDEX')
    add(metadata, 'Value', '1')
    shell = component('oobeSystem', 'Microsoft-Windows-Shell-Setup')
    add(add(shell, 'OOBE'), 'HideOnlineAccountScreens', 'true')
    deployment = component('specialize', 'Microsoft-Windows-Deployment')
    cmd = add(add(deployment, 'RunSynchronous'), 'RunSynchronousCommand', **{'{' + wcm + '}action': 'add'})
    add(cmd, 'Order', '1')
    add(cmd, 'Description', 'Apply Tiny11 package choices and register component cleanup')
    add(cmd, 'Path', r'%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%WINDIR%\Setup\Tiny11MacOS\Service-Tiny11.ps1" -Phase Provision')
    add(cmd, 'WillReboot', 'Never')
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def build(args):
    source = Path(args.source).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    scratch = Path(args.scratch).expanduser().resolve()
    tool = ROOT / '.deps/wimlib/bin/wimlib-imagex'
    if not tool.is_file():
        raise RuntimeError('Build metadata-preserving wimlib first; see README.md')
    for name in ('mkisofs', 'hdiutil', 'xorriso'):
        if not shutil.which(name):
            raise RuntimeError(f'Missing {name}; see README.md')
    if destination.exists() or scratch.exists():
        raise RuntimeError('Output and scratch paths must be new; existing paths are never overwritten')
    if source.is_file() and getattr(source.stat(), 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0x40000000):
        raise RuntimeError('Source ISO is offloaded. In Finder choose Download Now/Keep Downloaded before building.')
    if scratch in destination.parents or scratch == destination:
        raise RuntimeError('ISO output must be outside the scratch tree')
    if not 1 <= args.index:
        raise RuntimeError('Edition index must be positive')
    config = load(args.upstream)
    mount = None
    if source.is_file() and source.suffix.lower() == '.iso':
        mounted = command(['hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', source], capture=True)
        import plistlib
        entries = plistlib.loads(mounted.encode())['system-entities']
        mount = next((entry['mount-point'] for entry in entries if 'mount-point' in entry), None)
        if not mount:
            raise RuntimeError('ISO mounted without a filesystem mount point')
        media = Path(mount)
    elif source.is_dir():
        media = source
    else:
        raise RuntimeError('Source must be a Windows x64 ISO or mounted setup directory')
    try:
        install = next((media / 'sources' / name for name in ('install.wim', 'install.esd')
                        if (media / 'sources' / name).is_file()), None)
        if not install:
            raise RuntimeError('No install.wim or install.esd found')
        if getattr(install.stat(), 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0x40000000):
            raise RuntimeError('Install image is offloaded. In Finder choose Download Now/Keep Downloaded first.')
        for relative in ('sources/boot.wim', 'boot/etfsboot.com', 'efi/microsoft/boot/efisys.bin'):
            candidate = media / relative
            if candidate.is_file() and getattr(candidate.stat(), 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0x40000000):
                raise RuntimeError(f'{relative} is offloaded. In Finder choose Download Now/Keep Downloaded first.')
        info = command([tool, 'info', install, str(args.index)], capture=True)
        if not re.search(r'(?im)^\s*Architecture:\s*(x64|amd64|x86_64)\s*$', info):
            raise RuntimeError('Selected edition is not x64')
        if shutil.disk_usage(destination.parent if destination.parent.exists() else ROOT).free < 20 * 1024**3:
            raise RuntimeError('At least 20 GiB free space is required for this build')
        scratch.mkdir(parents=True)
        tree = scratch / 'media'
        shutil.copytree(media, tree, ignore=shutil.ignore_patterns('install.wim', 'install.esd'))
        for entry in tree.rglob('*'):
            entry.chmod(0o755 if entry.is_dir() else 0o644)
        tree.chmod(0o755)
        target_wim = tree / 'sources/install.wim'
        command([tool, 'export', install, str(args.index), target_wim, '--compress=LZX', '--threads=1'])
        report = {'mode': 'native-build-deferred-target-servicing', 'full_offline_parity': False,
                  'target_servicing_verified': False, 'source': str(source), 'index': args.index,
                  'edition_info': info, 'upstream_commit': config['upstream_commit']}
        report['install_registry'] = rewrite_hives(target_wim, 1, config['install'], scratch / 'install-hives', tool)
        report['boot_registry'] = rewrite_hives(tree / 'sources/boot.wim', 2, config['boot'], scratch / 'boot-hives', tool)
        deletion_commands = [f'delete --force --recursive {quoted("/" + path)}' for path in config['files_to_delete']]
        command([tool, 'update', target_wim, '1'], input='\n'.join(deletion_commands) + '\n')
        report['file_deletions'] = config['files_to_delete']
        payload = scratch / 'payload'
        payload.mkdir()
        shutil.copy2(ROOT / 'target/Service-Tiny11.ps1', payload / 'Service-Tiny11.ps1')
        (payload / 'config.json').write_text(json.dumps(config, indent=2))
        answer_file(tree / 'autounattend.xml')
        command([tool, 'update', target_wim, '1'], input=(
            f'add {quoted(payload)} "/Windows/Setup/Tiny11MacOS"\n'
            f'add {quoted(tree / "autounattend.xml")} "/Windows/System32/Sysprep/autounattend.xml"\n'))
        # Ensure all referenced deletions are absent in the actual archive.
        listing = command([tool, 'dir', target_wim, '1'], capture=True)
        for path in config['files_to_delete']:
            if '/' + path.casefold() in listing.casefold().splitlines():
                raise RuntimeError(f'Deleted path still present: {path}')
        command([tool, 'optimize', target_wim, '--compress=LZMS:' + str(args.compression_level),
                 '--solid', '--threads=' + str(args.threads)])
        report['compression'] = {'algorithm': 'LZMS', 'level': args.compression_level, 'threads': args.threads}
        command([tool, 'verify', target_wim])
        command([tool, 'verify', tree / 'sources/boot.wim'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_iso = destination.with_suffix(destination.suffix + '.partial')
        if temporary_iso.exists():
            raise RuntimeError('Temporary ISO path already exists')
        command(['mkisofs', '-o', temporary_iso, '-udf', '-iso-level', '3', '-J', '-joliet-long',
                 '-V', 'TINY11_MACOS', '-b', 'boot/etfsboot.com', '-no-emul-boot', '-boot-load-size', '8',
                 '-eltorito-alt-boot', '-eltorito-platform', 'efi', '-b', 'efi/microsoft/boot/efisys.bin',
                 '-no-emul-boot', tree])
        report['boot_catalog'] = command(['xorriso', '-indev', temporary_iso, '-report_el_torito', 'plain'], capture=True)
        if 'BIOS' not in report['boot_catalog'] or 'UEFI' not in report['boot_catalog']:
            raise RuntimeError('Output ISO does not contain both BIOS and EFI boot entries')
        temporary_iso.rename(destination)
        sha = hashlib.sha256()
        with destination.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b''):
                sha.update(block)
        report['iso_sha256'] = sha.hexdigest()
        report['iso_bytes'] = destination.stat().st_size
        destination.with_suffix('.report.json').write_text(json.dumps(report, indent=2))
        print(f'Built experimental installer: {destination}\nTarget package servicing remains unverified.')
        return 0
    finally:
        if mount:
            command(['hdiutil', 'detach', mount])
