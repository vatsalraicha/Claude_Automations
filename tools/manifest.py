#!/usr/bin/env python3
"""Manifest helper shared by every loop. Standard library only.

A manifest is a CSV file with one row per item (page, repo, ticket).
The first column is the key. Every manifest has `status`, `attempts` and `notes` columns.

Statuses:
  pending      not processed yet
  done         worker finished, not yet checked
  verified     checker passed   (set only by the verify scripts, never by hand)
  failed       checker failed, will be retried
  needs_human  failed MAX_ATTEMPTS times, or needs a person to decide

Commands:
  init    <manifest> --columns a,b,c
  add     <manifest> --jsonl rows.jsonl [--update]
  next    <manifest> [--n 10] [--status failed,pending] [--where field=value] [--fields a,b]
  get     <manifest> <key>
  set     <manifest> <key[,key,...]> field=value [field=value ...]
  fail    <manifest> <key> --note "what failed"
  bulk    <manifest> --where field=value --set field=value
  counts  <manifest>
  diff    <manifest> <other> [--fields version,title]
"""
import argparse
import csv
import datetime
import json
import os
import sys
import tempfile
from collections import Counter

MAX_ATTEMPTS = 3
REQUIRED = ["status", "attempts", "notes"]


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def read_manifest(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        fields = list(reader.fieldnames or [])
    return fields, rows


def write_manifest(path, fields, rows):
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})
    os.replace(tmp, path)


def key_field(fields):
    return fields[0]


def find_row(fields, rows, key):
    kf = key_field(fields)
    for row in rows:
        if row.get(kf) == str(key):
            return row
    return None


def add_note(row, note):
    note = " ".join(str(note).split())
    if not note:
        return
    old = row.get("notes", "") or ""
    row["notes"] = (old + " | " if old else "") + note


def mark_failed(row, note, max_attempts=MAX_ATTEMPTS):
    """Record one failed attempt. Returns the new status."""
    attempts = int(row.get("attempts") or 0) + 1
    row["attempts"] = str(attempts)
    row["status"] = "needs_human" if attempts >= max_attempts else "failed"
    add_note(row, "[%s] attempt %d failed: %s" % (now(), attempts, note))
    return row["status"]


def mark_verified(row):
    row["status"] = "verified"
    if "verified_at" in row:
        row["verified_at"] = now()


def parse_pairs(pairs):
    out = {}
    for p in pairs:
        if "=" not in p:
            sys.exit("Expected field=value, got: %s" % p)
        k, v = p.split("=", 1)
        out[k] = v
    return out


def cmd_init(a):
    if os.path.exists(a.manifest):
        sys.exit("Refusing to overwrite existing manifest: %s" % a.manifest)
    fields = [c.strip() for c in a.columns.split(",") if c.strip()]
    for req in REQUIRED:
        if req not in fields:
            fields.append(req)
    write_manifest(a.manifest, fields, [])
    print("Created %s with columns: %s" % (a.manifest, ", ".join(fields)))


def cmd_add(a):
    fields, rows = read_manifest(a.manifest)
    kf = key_field(fields)
    index = {r[kf]: r for r in rows}
    added = updated = skipped = 0
    with open(a.jsonl, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError as e:
                sys.exit("Line %d of %s is not valid JSON: %s" % (n, a.jsonl, e))
            unknown = [k for k in item if k not in fields]
            if unknown:
                sys.exit("Line %d has fields not in the manifest: %s" % (n, ", ".join(unknown)))
            if not str(item.get(kf, "")).strip():
                sys.exit("Line %d has no value for key column '%s'" % (n, kf))
            key = str(item[kf])
            if item.get("status") == "verified":
                sys.exit("Line %d: rows cannot be added as verified." % n)
            if key in index:
                if a.update:
                    for k, v in item.items():
                        index[key][k] = "" if v is None else str(v)
                    updated += 1
                else:
                    skipped += 1
                continue
            row = {k: "" for k in fields}
            for k, v in item.items():
                row[k] = "" if v is None else str(v)
            row["status"] = row["status"] or "pending"
            row["attempts"] = row["attempts"] or "0"
            rows.append(row)
            index[key] = row
            added += 1
    write_manifest(a.manifest, fields, rows)
    print("added=%d updated=%d skipped_existing=%d total=%d" % (added, updated, skipped, len(rows)))


def cmd_next(a):
    fields, rows = read_manifest(a.manifest)
    statuses = [s.strip() for s in a.status.split(",")]
    where = parse_pairs(a.where or [])
    wanted = [f.strip() for f in a.fields.split(",")] if a.fields else fields
    picked = []
    for status in statuses:  # earlier statuses in the list are served first
        for row in rows:
            if row.get("status") != status:
                continue
            if any(row.get(k) != v for k, v in where.items()):
                continue
            picked.append(row)
    for row in picked[: a.n]:
        print(json.dumps({k: row.get(k, "") for k in wanted}, ensure_ascii=False))
    if not picked:
        print("NO_ROWS status in (%s)" % a.status, file=sys.stderr)


def cmd_get(a):
    fields, rows = read_manifest(a.manifest)
    row = find_row(fields, rows, a.key)
    if row is None:
        sys.exit("No row with key %s" % a.key)
    print(json.dumps(row, ensure_ascii=False, indent=2))


def cmd_set(a):
    """<key> may be one key or several separated by commas."""
    fields, rows = read_manifest(a.manifest)
    updates = parse_pairs(a.pairs)
    for k, v in updates.items():
        if k not in fields:
            sys.exit("Unknown column: %s" % k)
        if k == "status" and v == "verified":
            sys.exit("status=verified can only be set by a verify script. Run the verify script instead.")
    keys = [k.strip() for k in a.key.split(",") if k.strip()]
    targets = []
    for key in keys:
        row = find_row(fields, rows, key)
        if row is None:
            sys.exit("No row with key %s (nothing was changed)" % key)
        targets.append(row)
    for row in targets:
        for k, v in updates.items():
            if k == "notes":
                add_note(row, v)
            else:
                row[k] = v
    write_manifest(a.manifest, fields, rows)
    print("updated %d row(s): %s" % (len(keys), ", ".join(keys)))


def cmd_fail(a):
    fields, rows = read_manifest(a.manifest)
    row = find_row(fields, rows, a.key)
    if row is None:
        sys.exit("No row with key %s" % a.key)
    status = mark_failed(row, a.note)
    write_manifest(a.manifest, fields, rows)
    print("%s -> %s (attempts=%s)" % (a.key, status, row["attempts"]))


def cmd_bulk(a):
    fields, rows = read_manifest(a.manifest)
    where = parse_pairs(a.where)
    updates = parse_pairs(a.set)
    if updates.get("status") == "verified":
        sys.exit("status=verified can only be set by a verify script.")
    for k in list(where) + list(updates):
        if k not in fields:
            sys.exit("Unknown column: %s" % k)
    n = 0
    for row in rows:
        if all(row.get(k) == v for k, v in where.items()):
            row.update(updates)
            n += 1
    write_manifest(a.manifest, fields, rows)
    print("updated %d rows" % n)


def cmd_counts(a):
    fields, rows = read_manifest(a.manifest)
    counts = Counter(r.get("status", "") or "(blank)" for r in rows)
    out = {"total": len(rows)}
    out.update(dict(sorted(counts.items())))
    open_rows = sum(counts.get(s, 0) for s in ("pending", "done", "failed"))
    out["still_open"] = open_rows
    print(json.dumps(out))


def cmd_diff(a):
    fa, ra = read_manifest(a.manifest)
    fb, rb = read_manifest(a.other)
    ka, kb = key_field(fa), key_field(fb)
    ia = {r[ka]: r for r in ra}
    ib = {r[kb]: r for r in rb}
    compare = [f.strip() for f in a.fields.split(",") if f.strip()]
    only_a = sorted(set(ia) - set(ib))
    only_b = sorted(set(ib) - set(ia))
    changed = []
    for key in sorted(set(ia) & set(ib)):
        diffs = {f: [ia[key].get(f, ""), ib[key].get(f, "")] for f in compare
                 if ia[key].get(f, "") != ib[key].get(f, "")}
        if diffs:
            changed.append({"key": key, "changes": diffs})
    print(json.dumps({
        "only_in_first": only_a, "only_in_second": only_b, "changed": changed,
        "summary": {"only_in_first": len(only_a), "only_in_second": len(only_b), "changed": len(changed)},
    }, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("manifest"); s.add_argument("--columns", required=True)
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("add"); s.add_argument("manifest"); s.add_argument("--jsonl", required=True)
    s.add_argument("--update", action="store_true"); s.set_defaults(fn=cmd_add)

    s = sub.add_parser("next"); s.add_argument("manifest"); s.add_argument("--n", type=int, default=10)
    s.add_argument("--status", default="failed,pending"); s.add_argument("--where", action="append")
    s.add_argument("--fields"); s.set_defaults(fn=cmd_next)

    s = sub.add_parser("get"); s.add_argument("manifest"); s.add_argument("key"); s.set_defaults(fn=cmd_get)

    s = sub.add_parser("set"); s.add_argument("manifest"); s.add_argument("key")
    s.add_argument("pairs", nargs="+"); s.set_defaults(fn=cmd_set)

    s = sub.add_parser("fail"); s.add_argument("manifest"); s.add_argument("key")
    s.add_argument("--note", required=True); s.set_defaults(fn=cmd_fail)

    s = sub.add_parser("bulk"); s.add_argument("manifest")
    s.add_argument("--where", action="append", required=True)
    s.add_argument("--set", action="append", required=True); s.set_defaults(fn=cmd_bulk)

    s = sub.add_parser("counts"); s.add_argument("manifest"); s.set_defaults(fn=cmd_counts)

    s = sub.add_parser("diff"); s.add_argument("manifest"); s.add_argument("other")
    s.add_argument("--fields", default=""); s.set_defaults(fn=cmd_diff)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
