import importlib.util
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class InventoryTests(unittest.TestCase):
    def test_inventory_hash_and_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'read.txt').write_text('evidence')
            (root/'unknown.bin').write_bytes(b'\x00')
            docs, texts = runner.inventory(root)
            self.assertEqual([x['status'] for x in docs], ['readable', 'unsupported'])
            self.assertEqual(docs[0]['sha256'], 'ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e')
            self.assertEqual(texts[0]['pages'][0]['page'], None)
    def test_image_ocr_is_flagged_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'scan.png').write_bytes(b'image')
            with patch.object(runner, 'command', return_value=type('Result', (), {'returncode': 0, 'stdout': 'OCR text'})()):
                docs, texts = runner.inventory(root)
            self.assertEqual(docs[0]['status'], 'ocr_needs_review')
            self.assertEqual(texts[0]['pages'][0]['method'], 'ocr')

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): runner.inventory(root)

if __name__ == '__main__': unittest.main()
