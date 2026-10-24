import json, tempfile, unittest, hashlib
from pathlib import Path
from export_audit import audit, fixture

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root)
    def mutate(self, filename, fn):
        p = self.root / filename
        rows = json.loads(p.read_text()); fn(rows); p.write_text(json.dumps(rows))
    def types(self):
        return {x["type"] for x in audit(self.root)["findings"]}
    def test_intact_archive(self):
        self.assertTrue(audit(self.root)["complete_under_manifest_checks"])
    def test_missing_attachment(self):
        (self.root / "attachments/receipt.txt").unlink()
        self.assertEqual(self.types(), {"missing_attachment"})
    def test_content_change(self):
        self.mutate("messages_01.json", lambda x: x[0].update(text="Changed"))
        self.assertIn("hash_mismatch", self.types())
    def test_missing_batch(self):
        (self.root / "messages_01.json").unlink()
        self.assertEqual(self.types(), {"missing_batch", "source_count_mismatch"})
    def test_duplicate_id_preserved_and_flagged(self):
        self.mutate("messages_01.json", lambda x: x[1].update(id="M1"))
        self.assertIn("duplicate_id", self.types())
        self.assertEqual(audit(self.root)["exported_counts"]["messages"], 2)
    def test_orphan_reference(self):
        self.mutate("messages_01.json", lambda x: x[1].update(reservation_id="R999"))
        self.assertIn("unresolved_reservation", self.types())
    def test_missing_id(self):
        self.mutate("messages_01.json", lambda x: x[0].pop("id"))
        self.assertIn("missing_id", self.types())
    def test_count_discrepancy(self):
        self.mutate("messages_01.json", lambda x: x.pop())
        self.assertIn("batch_count_mismatch", self.types())
        self.assertIn("source_count_mismatch", self.types())
    def test_escape_is_refused(self):
        self.mutate("messages_01.json", lambda x: x[0].update(attachments=["../outside.txt"]))
        with self.assertRaises(ValueError): audit(self.root)
    def test_repeat_audit_does_not_modify_archive(self):
        before = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file()}
        first, second = audit(self.root), audit(self.root)
        after = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(first, second); self.assertEqual(before, after)
if __name__ == "__main__": unittest.main()
