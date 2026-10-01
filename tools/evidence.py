#!/usr/bin/env python3
"""Shared evidence checks used by the verify scripts. Standard library only.

Citation format in prose documents:   (src: path/to/file.ext:LINE)   or   (src: path/to/file.ext:LINE-LINE)
Citation format in JSON fields:       "path/to/file.ext:LINE"        or   "repo-name:path/to/file.ext:LINE"
"""
import re
from pathlib import Path

PROSE_CITATION = re.compile(r"\(src:\s*([^:()]+?):(\d+)(?:-(\d+))?\)")
SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Atlassian API token", re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}\b")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9_\-.=]{30,}\b")),
    ("password assignment", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"][^'\"\s<\[{$]{8,}['\"]")),
]

_line_cache = {}


def file_lines(path):
    path = Path(path)
    key = str(path)
    if key not in _line_cache:
        try:
            _line_cache[key] = path.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            _line_cache[key] = None
    return _line_cache[key]


def repo_dirname(repo):
    return repo.replace("/", "__")


def split_json_citation(value):
    """'path:12' -> (None, 'path', 12, 12); 'repo:path:12-20' -> ('repo', 'path', 12, 20). None if malformed."""
    m = re.match(r"^(?:([^:]+):)?([^:]+):(\d+)(?:-(\d+))?$", (value or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip(), int(m.group(3)), int(m.group(4) or m.group(3))


def check_location(repo_dir, path, start, end=None):
    """Does path exist inside repo_dir and does it have that many lines? Returns (ok, detail)."""
    repo_dir = Path(repo_dir).resolve()
    target = (repo_dir / path).resolve()
    if repo_dir != target and repo_dir not in target.parents:
        return False, "%s points outside the repository" % path
    if not target.is_file():
        return False, "%s does not exist" % path
    lines = file_lines(target)
    if lines is None:
        return False, "%s cannot be read" % path
    end = end or start
    if start < 1 or end < start or end > len(lines):
        return False, "%s has %d lines, cited %d-%d" % (path, len(lines), start, end)
    return True, "ok"


def prose_citations(text):
    return [(m.group(1).strip(), int(m.group(2)), int(m.group(3) or m.group(2))) for m in PROSE_CITATION.finditer(text)]


def normalise(text):
    """Make quotes comparable: drop markdown markers and escapes, unify quotes and whitespace."""
    text = text.replace(" ", " ")
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[“”]", '"', text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"[\\*`_|>#]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_found(quote, haystack):
    q = normalise(quote)
    return bool(q) and q in normalise(haystack)


def quote_near_line(repo_dir, path, line, quote, window=20):
    """Is the quote present in the file within `window` lines of the cited line? Returns (ok, detail)."""
    ok, detail = check_location(repo_dir, path, line)
    if not ok:
        return False, detail
    lines = file_lines(Path(repo_dir) / path)
    lo, hi = max(0, line - 1 - window), min(len(lines), line + window)
    if quote_found(quote, "\n".join(lines[lo:hi])):
        return True, "ok"
    if quote_found(quote, "\n".join(lines)):
        return False, "quote is in %s but not near line %d" % (path, line)
    return False, "quote not found in %s" % path


def word_count(text):
    return len(re.findall(r"\S+", text or ""))


def find_secrets(text):
    return [label for label, rx in SECRET_PATTERNS if rx.search(text)]
