"""Guard: no raw data, outputs or customer IDs in tracked files.

Usage:
    git ls-files -z | xargs -0 python scripts/check_no_data.py
    python scripts/check_no_data.py <path> ...

Fails (exit 1) if any listed file is under data/raw/, data/interim/,
outputs/, config/local/ or evidence/ (except .gitkeep), or has a
data extension (csv, tsv, xlsx, xls, parquet), or if a tracked text
file contains a pattern like a Google Ads customer ID (three digits,
dash, three digits, dash, four digits). Lists offending paths only,
never the matched text.

find_offending() takes a list of (path, content) pairs, where content
is bytes/str or None, so it can be tested without git.
"""

import re
import sys
from pathlib import PurePosixPath

# Folders that must never be tracked (except .gitkeep files).
FORBIDDEN_DIRS = ("data/raw/", "data/interim/", "outputs/",
                  "config/local/", "evidence/")
FORBIDDEN_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
# A possible Google Ads customer ID: three digits, dash, three
# digits, dash, four digits.
CUSTOMER_ID_RE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")


def find_offending(files):
    """Return the sorted list of offending paths from (path, content)."""
    offending = []
    for path, content in files:
        posix = PurePosixPath(str(path).replace("\\", "/")).as_posix()
        name = PurePosixPath(posix).name
        reason = None
        if name != ".gitkeep" and any(
            posix == d.rstrip("/") or posix.startswith(d)
            for d in FORBIDDEN_DIRS
        ):
            reason = "forbidden folder"
        elif PurePosixPath(posix).suffix.lower() in FORBIDDEN_EXTENSIONS:
            reason = "data extension"
        if reason is None and content is not None:
            if isinstance(content, bytes):
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    text = content.decode("utf-8", errors="ignore")
            else:
                text = str(content)
            if CUSTOMER_ID_RE.search(text):
                reason = "possible customer ID"
        if reason is not None:
            offending.append(posix)
    return sorted(set(offending))


def main(argv=None):
    """Read listed paths from argv (or stdin), check them, exit 1 if any."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = [line.strip() for line in sys.stdin if line.strip()]
    files = []
    for path in args:
        try:
            content = open(path, "rb").read()
        except OSError:
            # Missing/unreadable file: path rules still apply.
            content = None
        files.append((path, content))
    offending = find_offending(files)
    if offending:
        print("FAIL: data or customer IDs found in tracked files:")
        for path in offending:
            print(f"  {path}")
        return 1
    print("PASS: no data files or customer IDs in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
