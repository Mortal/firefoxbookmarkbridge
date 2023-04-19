import glob
import os
import sqlite3

import url_hash


ROOTS = ("root", "menu", "toolbar", "tags", "unfiled", "mobile")


guid_to_root = {
    "root": "placesRoot",
    "menu": "bookmarksMenuFolder",
    "toolbar": "toolbarFolder",
    "unfiled": "unfiledBookmarksFolder",
    "mobile": "mobileFolder",
}


def guess_places_path() -> str:
    return max(
        glob.glob(
            os.path.expanduser("~/.mozilla/firefox/*.default*/places.sqlite")
        ),
        key=lambda f: os.stat(f).st_mtime,
    )


def dump_bookmarks(cur):

    def visit_root(guid: str):
        assert guid in ROOTS
        cur.execute(
            """SELECT
            moz_bookmarks.id,
            moz_bookmarks.type,
            moz_bookmarks.fk,
            moz_bookmarks.position,
            moz_bookmarks.title,
            moz_bookmarks.dateAdded,
            moz_bookmarks.lastModified,
            moz_bookmarks.guid,
            moz_places.url,
            moz_places.url_hash
            FROM moz_bookmarks
            LEFT JOIN moz_places ON moz_places.id = moz_bookmarks.fk
            WHERE moz_bookmarks.guid = ?
            ORDER BY position""",
            (guid.ljust(12, "_"),)
        )
        row, = cur
        return _visit_row(row, skip=("tags",))

    def visit(folder_id: int, skip=()):
        cur.execute(
            """SELECT
            moz_bookmarks.id,
            moz_bookmarks.type,
            moz_bookmarks.fk,
            moz_bookmarks.position,
            moz_bookmarks.title,
            moz_bookmarks.dateAdded,
            moz_bookmarks.lastModified,
            moz_bookmarks.guid,
            moz_places.url,
            moz_places.url_hash
            FROM moz_bookmarks
            LEFT JOIN moz_places ON moz_places.id = moz_bookmarks.fk
            WHERE parent = ?
            ORDER BY position""",
            (folder_id,),
        )
        return [_visit_row(row) for row in list(cur) if (not skip or row[7].rstrip("_") not in skip)]

    def _visit_row(row, skip=()):
        (
            id,
            type,
            fk,
            position,
            title,
            date_added,
            last_modified,
            guid,
            url,
            uh,
        ) = row
        if title is None:
            title = ""
        base = {
            "guid": guid,
            "title": title,
            "index": position,
            "dateAdded": date_added,
            "lastModified": last_modified,
            "id": id,
            "typeCode": type,
            "type": {1: "text/x-moz-place", 2: "text/x-moz-place-container"}[type],
        }
        if guid.rstrip("_") in guid_to_root:
            base["root"] = guid_to_root[guid.rstrip("_")]
        if fk is not None:
            assert fk is not None
            assert url is not None
            assert uh is not None
            assert uh == 0 or url_hash.url_hash(url) == uh, (url, uh, url_hash.url_hash(url))
            base["uri"] = url
        children = visit(id, skip=skip)
        if children:
            base["children"] = children
        return base

    return visit_root("root")


def json_to_rows(a):
    rows: dict = {}

    def visit(a, parent):
        assert a["guid"] not in rows
        assert not rows or a["guid"] != parent
        row = {
            "parent": parent,
            "title": a["title"],
            "index": a["index"],
            "dateAdded": a["dateAdded"],
            "lastModified": a["lastModified"],
        }
        if "uri" in a:
            row["uri"] = a["uri"]
            assert a["typeCode"] == 1
        else:
            assert a["typeCode"] == 2
        rows[a["guid"]] = row
        assert parent in rows
        for o in a.get("children", ()):
            visit(o, a["guid"])

    visit(a, a["guid"])
    return rows


def diff_dicts(a_rows, b_rows):
    only_in_a = {
        guid: row
        for guid, row in a_rows.items()
        if guid not in b_rows
    }
    only_in_b = {
        guid: row
        for guid, row in b_rows.items()
        if guid not in a_rows
    }
    changed = {
        guid: (a_rows[guid], b_rows[guid])
        for guid in a_rows
        if guid in b_rows and a_rows[guid] != b_rows[guid]
    }
    return (only_in_a, changed, only_in_b)


def print_diff(diff, a_path, b_path):
    only_in_a, changed, only_in_b = diff
    if only_in_a:
        print("Only in %s:" % a_path)
    for guid, o in only_in_a.items():
        print("- %s %s" % (o["title"], o["uri"] if "uri" in o else "(folder)"))
    if only_in_b:
        print("Only in %s:" % b_path)
    for guid, o in only_in_b.items():
        print("- %s %s" % (o["title"], o["uri"] if "uri" in o else "(folder)"))
    if changed:
        print("Changed:")
    for guid, (old, o) in changed.items():
        line = ["-"]
        if old["title"] == o["title"]:
            line.append(o["title"])
        else:
            line.append("%s -> %s" % (old["title"], o["title"]))
        if "uri" in o:
            assert "uri" in old
            if old["uri"] == o["uri"]:
                line.append(o["uri"])
            else:
                line.append("%s -> %s" % (old["uri"], o["uri"]))
        else:
            assert "uri" not in old
            line.append("(folder)")
        for k in o:
            if o.get(k) != old.get(k):
                line.append("[%s: %s -> %s]" % (k, old.get(k), o.get(k)))
        print(" ".join(line))
