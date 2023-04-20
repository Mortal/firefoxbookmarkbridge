import argparse
import base64
import datetime
import json
import os
import random
import subprocess
import sqlite3

import firefoxbookmarkdatabase
import firefoxbookmarkdiff
import url_hash


parser = argparse.ArgumentParser()
parser.add_argument("--places-path")
parser.add_argument("-n", "--no-backup", action="store_true")
parser.add_argument("-f", "--no-confirm", action="store_true")
parser.add_argument("-s", "--silent", action="store_true")
parser.add_argument("path")


def generate_guid() -> str:
    # NS_GeneratePlacesGUID aka mozilla::places::GenerateGUID
    # https://searchfox.org/mozilla-central/source/toolkit/components/places/Helpers.cpp
    return base64.urlsafe_b64encode(random.randbytes(9)).decode()


def main() -> None:
    args = parser.parse_args()

    with open(args.path) as fp:
        path_contents = json.load(fp)
    path_rows = firefoxbookmarkdatabase.json_to_rows(path_contents)

    places_path: str | None = args.places_path
    if places_path is None:
        places_path = firefoxbookmarkdatabase.guess_places_path()
    if not places_path.startswith("/"):
        places_path = os.path.abspath(places_path)
    assert places_path.endswith(".sqlite")
    places_path_base = places_path.rpartition(".sqlite")[0]
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args.no_backup:
        backup_path = places_path_base + "_before_%s.sqlite" % now
        subprocess.check_call(("sqlite3", places_path, ".backup %s" % backup_path))
    db = sqlite3.connect(places_path)
    cur = db.cursor()
    db_dump = firefoxbookmarkdatabase.dump_bookmarks(cur)
    if not args.no_backup:
        backup_path = places_path_base + "_before_%s.json" % now
        with open(backup_path, "w") as fp:
            fp.write(json.dumps(db_dump) + "\n")
    db_rows = firefoxbookmarkdatabase.json_to_rows(db_dump)
    only_in_db, changed, only_in_path = firefoxbookmarkdatabase.diff_dicts(
        db_rows, path_rows
    )
    if not only_in_db and not changed and not only_in_path:
        if not args.silent:
            print("No changes")
        return
    if not args.silent:
        firefoxbookmarkdatabase.print_diff(
            (only_in_db, changed, only_in_path), places_path, args.path
        )
    if not args.no_confirm:
        inp = "a"
        while inp != "":
            try:
                inp = input(
                    "Really import the above changes? Press CTRL-C to abort, or RETURN to proceed."
                )
            except (EOFError, KeyboardInterrupt):
                print("\nAborting.")
                return
    apply_changes(cur, only_in_db, changed, only_in_path)
    cur.close()
    del cur
    db.commit()
    db.close()
    del db


def topsort(only_in):
    roots = []
    childlists = {}
    for guid, row in only_in.items():
        if row["parent"] in only_in and row["parent"] != guid:
            childlists.setdefault(row["parent"], []).append(guid)
        else:
            roots.append(guid)

    result = []

    def visit(guid):
        result.append(guid)
        for c in childlists.get(guid, ()):
            visit(c)

    for guid in roots:
        visit(guid)
    assert len(result) == len(only_in)
    return result


def apply_changes(cur, only_in_db, changed, only_in_path):
    TRACE = 1

    def guid_to_id(guid) -> int:
        cur.execute("SELECT id FROM moz_bookmarks WHERE guid = ?", (guid,))
        (row,) = cur
        (id,) = row
        assert isinstance(id, int)
        return id

    def origin_id_and_host(uri) -> tuple[int, str]:
        scheme, sep, rest = uri.partition("://")
        if not sep:
            scheme, sep, rest = uri.partition(":")
        assert sep, uri
        prefix = scheme + sep
        host = rest.split("/")[0]
        cur.execute(
            "SELECT id FROM moz_origins WHERE prefix = ? AND host = ?", (prefix, host)
        )
        rows = list(cur)
        if rows:
            (row,) = rows
            (id,) = row
            assert isinstance(id, int)
            return id, host
        TRACE and print("INSERT INTO moz_origins", (uri, prefix, host))
        cur.execute(
            "INSERT INTO moz_origins (prefix, host, frecency) VALUES (?, ?, 0)",
            (prefix, host),
        )
        TRACE and print(cur.lastrowid)
        return cur.lastrowid, host

    def uri_to_fk(uri) -> int:
        cur.execute(
            "SELECT id FROM moz_places WHERE url_hash = ?", (url_hash.url_hash(uri),)
        )
        rows = list(cur)
        if rows:
            (row,) = rows
            (id,) = row
            assert isinstance(id, int)
            return id

        origin_id, host = origin_id_and_host(uri)
        TRACE and print("INSERT INTO moz_places", uri)
        cur.execute(
            "INSERT INTO moz_places (url, url_hash, title, rev_host, guid, origin_id) VALUES (?, ?, ?, ?, ?, ?)",
            (uri, url_hash.url_hash(uri), uri, host[::-1], generate_guid(), origin_id),
        )
        TRACE and print(cur.lastrowid)
        return cur.lastrowid

    for guid in topsort(only_in_path):
        row = only_in_path[guid]
        parent_id = 0 if guid == row["parent"] else guid_to_id(row["parent"])
        if "uri" in row:
            fk = uri_to_fk(row["uri"])
            type = 1
        else:
            fk = None
            type = 2
        TRACE and print("INSERT INTO moz_bookmarks", row["title"])
        cur.execute(
            "INSERT INTO moz_bookmarks (type, fk, parent, position, title, dateAdded, lastModified, guid) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                type,
                fk,
                parent_id,
                row["index"],
                row["title"],
                row["dateAdded"],
                row["lastModified"],
                guid,
            ),
        )
        TRACE and print(cur.lastrowid)

    for guid, (old, new) in changed.items():
        if "uri" in old:
            assert "uri" in new
            if old["uri"] != new["uri"]:
                TRACE and print("UPDATE moz_bookmarks SET fk", guid)
                cur.execute(
                    "UPDATE moz_bookmarks SET fk = ? WHERE guid = ?",
                    (uri_to_fk(new["uri"]), guid),
                )
                TRACE and print(cur.rowcount)
        else:
            assert "uri" not in new
        TRACE and print("UPDATE moz_bookmarks", guid, new["title"])
        cur.execute(
            "UPDATE moz_bookmarks SET position = ?, title = ?, dateAdded = ?, lastModified = ? WHERE guid = ?",
            (new["index"], new["title"], new["dateAdded"], new["lastModified"], guid),
        )
        TRACE and print(cur.rowcount)

    for guid in topsort(only_in_db)[::-1]:
        TRACE and print("DELETE FROM moz_bookmarks", guid, only_in_db[guid]["title"])
        cur.execute("DELETE FROM moz_bookmarks WHERE guid = ?", (guid,))
        TRACE and print(cur.rowcount)


if __name__ == "__main__":
    main()
