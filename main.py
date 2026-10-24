from export_audit import audit, fixture
from pathlib import Path
import json, tempfile
if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        fixture(d)
        clean = audit(d)
        Path(d, "attachments/receipt.txt").unlink()
        incomplete = audit(d)
        print(json.dumps({"intact_archive": clean, "missing_attachment_case": incomplete}, indent=2))
