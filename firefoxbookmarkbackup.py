"""
Produce the same output as Firefox's Organize bookmarks -> Backup format
(except without the favicons).
"""
import argparse
import json
import os
import sqlite3

import firefoxbookmarkdatabase


parser = argparse.ArgumentParser()
parser.add_argument("--places-path")
parser.add_argument("-f", "--overwrite", action="store_true")
parser.add_argument("output", nargs="?")


def main() -> None:
    args = parser.parse_args()
    places_path: str | None = args.places_path
    if places_path is None:
        places_path = firefoxbookmarkdatabase.guess_places_path()
    if not places_path.startswith("/"):
        places_path = os.path.abspath(places_path)
    db = sqlite3.connect("file://%s?mode=ro" % places_path, uri=True)
    cur = db.cursor()
    dumped = json.dumps(firefoxbookmarkdatabase.dump_bookmarks(cur), indent=2)
    if args.output is not None:
        with open(args.output, "w" if args.overwrite else "x") as fp:
            fp.write(dumped + "\n")
    else:
        print(dumped)


if __name__ == "__main__":
    main()
