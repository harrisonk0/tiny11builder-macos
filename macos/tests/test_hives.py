import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hives import Hive
from config import load


class NativeHiveTests(unittest.TestCase):
    def test_preserve_existing_values_and_unicode_roundtrip(self):
        fixture = Path('/opt/homebrew/share/hivex/test/large')
        if not fixture.exists():
            self.skipTest('hivex sample hive not installed')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'edited.hive'
            with Hive(fixture, write=True) as hive:
                hive.set('Tiny11Test', 'Existing', 'REG_SZ', 'keep this')
                hive.set('Tiny11Test', 'Added', 'REG_DWORD', '1')
                hive.set('Tiny11Test', 'Unicode', 'REG_SZ', 'café 🚴')
                hive.set('Tiny11Test', 'Added', 'REG_DWORD', '3')
                hive.set('Tiny11Test\\RemoveMe', 'A', 'REG_DWORD', '1')
                hive.delete('Tiny11Test\\RemoveMe')
                hive.commit(out)
            with Hive(out) as hive:
                self.assertEqual(hive.read('Tiny11Test', 'Existing'), Hive.encode('REG_SZ', 'keep this'))
                self.assertEqual(hive.read('Tiny11Test', 'Added'), Hive.encode('REG_DWORD', '3'))
                self.assertEqual(hive.read('Tiny11Test', 'Unicode'), Hive.encode('REG_SZ', 'café 🚴'))
                self.assertFalse(hive.node('Tiny11Test\\RemoveMe'))

    def test_real_system_hive_keeps_select_and_controlset(self):
        source = Path(__file__).resolve().parents[1] / 'real-test/hives/Windows/System32/config/SYSTEM'
        if not source.exists():
            self.skipTest('real media hive not available')
        with Hive(source) as hive:
            original = hive.read('Select', 'Current')
            controlset_start = hive.read('ControlSet001\\Services\\ACPI', 'Start')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'SYSTEM'
            with Hive(source, write=True) as hive:
                hive.set('Setup\\LabConfig', 'BypassCPUCheck', 'REG_DWORD', '1')
                hive.commit(out)
            with Hive(out) as hive:
                self.assertEqual(hive.read('Select', 'Current'), original)
                self.assertEqual(hive.read('ControlSet001\\Services\\ACPI', 'Start'), controlset_start)
                self.assertEqual(hive.read('Setup\\LabConfig', 'BypassCPUCheck'), Hive.encode('REG_DWORD', '1'))

    def test_audited_config_is_complete(self):
        repo_root = Path(__file__).resolve().parents[2]
        upstream = repo_root if (repo_root / 'tiny11maker.ps1').is_file() else repo_root / 'tiny11builder-upstream'
        config = load(upstream)
        self.assertEqual(len(config['install']), 61)
        self.assertEqual(len(config['boot']), 10)
        self.assertIn('Clipchamp.Clipchamp', config['package_prefixes'])
        self.assertTrue(any(op.get('name') == 'ConfigureStartPins' and op['value'] == '{"pinnedList": [{}]}'
                            for op in config['install']))


if __name__ == '__main__':
    unittest.main()
