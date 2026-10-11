import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer import answer_file, quoted


class InstallerTests(unittest.TestCase):
    def test_find_upstream_scripts_at_repository_root(self):
        repo_root = Path(__file__).resolve().parents[2]
        cli_path = Path(__file__).resolve().parents[1] / 'tiny11-macos.py'
        spec = importlib.util.spec_from_file_location('tiny11_macos_cli', cli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = repo_root if (repo_root / 'tiny11maker.ps1').is_file() else repo_root / 'tiny11builder-upstream'
        self.assertEqual(module.default_upstream(), str(expected))

    def test_answer_file_targets_single_exported_image_and_has_system_setup_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'autounattend.xml'
            answer_file(path)
            root = ET.parse(path).getroot()
        ns = {'u': 'urn:schemas-microsoft-com:unattend'}
        metadata = root.find("u:settings[@pass='windowsPE']//u:MetaData", ns)
        self.assertEqual(metadata.find('u:Key', ns).text, '/IMAGE/INDEX')
        self.assertEqual(metadata.find('u:Value', ns).text, '1')
        cmd = root.find("u:settings[@pass='specialize']//u:RunSynchronousCommand/u:Path", ns).text
        self.assertIn('Service-Tiny11.ps1', cmd)
        self.assertIn('-Phase Provision', cmd)
        self.assertIn('"%WINDIR%\\Setup\\Tiny11MacOS\\Service-Tiny11.ps1"', cmd)
        self.assertIsNone(root.find('.//u:DiskConfiguration', ns))
        self.assertIsNone(root.find('.//u:LocalAccounts', ns))
        self.assertIsNone(root.find('.//u:AcceptEula', ns))

    def test_wim_paths_reject_command_injection(self):
        for path in ('bad"path', 'bad\npath', 'bad\rpath'):
            with self.assertRaises(RuntimeError):
                quoted(path)
        self.assertEqual(quoted('/Program Files/a'), '"/Program Files/a"')


if __name__ == '__main__':
    unittest.main()
