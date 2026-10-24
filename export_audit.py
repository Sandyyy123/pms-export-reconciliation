"""Audit a previously exported synthetic PMS archive. No live PMS connector."""
import hashlib, json
from pathlib import Path

def safe_path(root, name):
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError("Archive path leaves export root")
    return p

def audit(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    findings, inventory, counts = [], [], {}
    records_by_kind = {}
    for batch in manifest["batches"]:
        path = safe_path(root, batch["file"])
        if not path.is_file():
            findings.append({"type": "missing_batch", "file": batch["file"]})
            continue
        content = path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != batch["sha256"]:
            findings.append({"type": "hash_mismatch", "file": batch["file"]})
        data = json.loads(content)
        if not isinstance(data, list):
            raise ValueError("Batch must contain a JSON array")
        if len(data) != batch["records"]:
            findings.append({"type": "batch_count_mismatch", "file": batch["file"],
                             "expected": batch["records"], "actual": len(data)})
        kind = batch["kind"]
        records_by_kind.setdefault(kind, []).extend(data)
        counts[kind] = counts.get(kind, 0) + len(data)
        inventory.append({"file": batch["file"], "bytes": len(content),
                          "sha256": actual_hash, "records": len(data)})
    for kind, expected in manifest["source_counts"].items():
        if counts.get(kind, 0) != expected:
            findings.append({"type": "source_count_mismatch", "kind": kind,
                             "expected": expected, "exported": counts.get(kind, 0)})
    for kind, records in records_by_kind.items():
        seen = set()
        for row in records:
            identifier = row.get("id")
            if identifier is None or identifier == "":
                findings.append({"type": "missing_id", "kind": kind})
            elif identifier in seen:
                findings.append({"type": "duplicate_id", "kind": kind, "id": identifier})
            else:
                seen.add(identifier)
            for name in row.get("attachments", []):
                if not safe_path(root, name).is_file():
                    findings.append({"type": "missing_attachment", "kind": kind,
                                     "id": identifier, "file": name})
    reservation_ids = {r.get("id") for r in records_by_kind.get("reservations", [])
                       if r.get("id") is not None}
    for row in records_by_kind.get("messages", []):
        ref = row.get("reservation_id")
        if ref is not None and ref not in reservation_ids:
            findings.append({"type": "unresolved_reservation", "message": row.get("id"),
                             "reservation_id": ref})
    return {"synthetic_demo": True, "source_counts": manifest["source_counts"],
            "exported_counts": counts, "inventory": inventory, "findings": findings,
            "complete_under_manifest_checks": not findings,
            "limitations": ["Source counts are supplied inputs, not independently fetched.",
                            "No Track PMS API, authentication or browser extraction is implemented.",
                            "Passing checks does not prove the source export contains every field."]}

def fixture(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    (root / "attachments").mkdir(exist_ok=True)
    (root / "attachments/receipt.txt").write_text("SYNTHETIC receipt; no client data")
    data = {"reservations_01.json": ("reservations", [
        {"id": "R1", "guest_id": "G1"}, {"id": "R2", "guest_id": "G2"}]),
        "messages_01.json": ("messages", [
        {"id": "M1", "reservation_id": "R1", "text": "Synthetic arrival message",
         "attachments": ["attachments/receipt.txt"]},
        {"id": "M2", "reservation_id": "R2", "text": "Synthetic checkout message"}])}
    batches = []
    for name, (kind, rows) in data.items():
        p = root / name; p.write_text(json.dumps(rows, indent=2))
        batches.append({"file": name, "kind": kind, "records": len(rows),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    (root / "manifest.json").write_text(json.dumps({
        "source_counts": {"reservations": 2, "messages": 2}, "batches": batches}, indent=2))

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("root"); p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo: fixture(a.root)
    print(json.dumps(audit(a.root), indent=2))
