"""Permanent, stdlib-only tests for the manual native JSON promotion classifier.

Run from repository root with:
  python -m unittest backend/app/services/structured_intake/test_json_content_only_profiles.py -v
The ZIP fixture models expanded APC leaf files; real Azure expander integration is
validated separately (the test does not execute the Azure Train Station).
"""
import hashlib
import sys
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p/'backend').is_dir() and (p/'frontend').is_dir())
sys.path.insert(0,str(PROJECT_ROOT/'backend'))
from app.services.structured_intake.promotion_profile import classify_promoted_json

FIXTURE = Path(__file__).with_name('test_json_content_only_fixture.zip')
EXPECTED = {
    '01_':'plain','02_':'plain','03_':'plain','04_':'plain','05_':'plain',
    '06_':'slack','07_':'slack','08_':'salesforce','09_':'salesforce',
    '10_':'teams','11_':'teams','12_':'google','13_':'google',
    '14_':'custom_api','15_':'custom_api','16_':'custom_api',
}

class ContentOnlyPromotionTests(unittest.TestCase):
    def test_expanded_zip_leaf_content_profiles_and_native_identity(self):
        with zipfile.ZipFile(FIXTURE) as archive:
            self.assertIsNone(archive.testzip())
            leaves = [m for m in archive.infolist() if not m.is_dir()]
            self.assertEqual(len(leaves),16)
            for child in leaves:
                with self.subTest(child=child.filename):
                    self.assertNotIn('..',Path(child.filename).parts)
                    self.assertFalse(child.filename.startswith('/'))
                    original = archive.read(child)
                    initial_hash = hashlib.sha256(original).hexdigest()
                    ext = Path(child.filename).suffix
                    actual = classify_promoted_json(original,child.filename,ext)
                    self.assertEqual(actual,EXPECTED[Path(child.filename).name[:3]])
                    for misleading_name in ('slack.json','teams.json','google.json','salesforce.json','random.json'):
                        self.assertEqual(classify_promoted_json(original,misleading_name,ext),actual)
                    self.assertEqual(hashlib.sha256(original).hexdigest(),initial_hash)

    def test_unknown_goes_custom_api(self):
        self.assertEqual(classify_promoted_json(b'{"other":{"value":1}}','slack.json','.json'),'custom_api')

    def test_first_decisive_vendor_wins_without_scanning_later_records(self):
        raw=(b'{"messages":[{"name":"spaces/a/messages/b","createTime":"t","sender":{"name":"users/a"}},'
             b'{"type":"message","ts":"1.0","user":"U1","text":"x"}]}')
        self.assertEqual(classify_promoted_json(raw,'example.json','.json'),'google')

    def test_jsonl_uses_multiple_records(self):
        raw=(b'{"arbitrary":1}\n'
             b'{"name":"spaces/a/messages/b","createTime":"t","sender":{"name":"users/a"}}\n')
        self.assertEqual(classify_promoted_json(raw,'other.jsonl','.jsonl'),'google')

    def test_non_json_extension_rejected(self):
        with self.assertRaises(ValueError):
            classify_promoted_json(b'{}','other.csv','.csv')

    def test_does_not_import_csv_generation(self):
        from app.services.structured_intake import promotion_profile
        import inspect
        source = inspect.getsource(promotion_profile)
        self.assertNotIn('to_csv(',source)
        self.assertNotIn('writerow(',source)

if __name__ == '__main__': unittest.main()

# Early-exit behavior is also verified by dedicated tests in
# test_json_profile_early_exit.py.
