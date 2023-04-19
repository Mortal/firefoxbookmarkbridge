import argparse
import json

import firefoxbookmarkdatabase


parser = argparse.ArgumentParser()
parser.add_argument("path", nargs="+")


def main() -> None:
    args = parser.parse_args()
    with open(args.path[0]) as fp:
        a = json.load(fp)
    a_rows = firefoxbookmarkdatabase.json_to_rows(a)
    with open(args.path[1]) as fp:
        b = json.load(fp)
    b_rows = firefoxbookmarkdatabase.json_to_rows(b)
    diff = firefoxbookmarkdatabase.diff_dicts(a_rows, b_rows)
    firefoxbookmarkdatabase.print_diff(diff, args.path[0], args.path[1])


if __name__ == "__main__":
    main()
