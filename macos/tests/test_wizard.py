import importlib.util
import sys
import unittest
from pathlib import Path

WIZARD_PATH = Path(__file__).resolve().parents[1] / 'build-wizard.py'
SPEC = importlib.util.spec_from_file_location('build_wizard', WIZARD_PATH)
WIZARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WIZARD)


class WizardTests(unittest.TestCase):
    def test_editions_offer_only_x64_images(self):
        info = """WIM Information:
Image Count: 2
Index: 1
Name: Windows ARM
Architecture: arm64
Index: 2
Name: Windows 11 Pro
Architecture: x86_64
"""
        self.assertEqual(WIZARD.editions(info), [(2, 'Windows 11 Pro', 'x86_64')])

    def test_edition_name_is_safe_for_filenames(self):
        self.assertEqual(WIZARD.safe_slug('Windows 11 Pro'), 'windows-11-pro')
        self.assertEqual(WIZARD.safe_slug('../../'), 'windows-x64')


if __name__ == '__main__':
    unittest.main()
