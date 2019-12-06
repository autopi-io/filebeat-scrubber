#!/usr/bin/env python3
# coding=utf-8

"""Generate random JSON files."""

import argparse
import datetime
import json
import os
import random
import time
import uuid


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generate random JSON files.")
    parser.add_argument(
        "--number",
        type=not_negative,
        dest="number",
        default=1,
        help="Number of JSON files to generate.",
    )
    parser.add_argument(
        "--delay",
        type=not_negative,
        dest="delay",
        default=0,
        help="Delay, in seconds, between generation of JSON files.",
    )
    parser.add_argument(
        "--array",
        action="store_true",
        dest="as_array",
        default=False,
        help="Generate JSON as an array of objects.",
    )
    parser.add_argument(
        "--indent",
        type=not_negative,
        dest="indent",
        default=4,
        help="Indent JSON by this many spaces. Use '0' to disable indentation.",
    )
    parser.add_argument(
        "--destination",
        type=str,
        dest="target_directory",
        default="tests/json_files",
        help="Directory to generate JSON files in.",
    )
    return parser.parse_args()


def not_negative(value: str) -> int:
    """Ensure a value is a a non-negative integer.

    :param value: Value from the command line.
    :return: The value as an integer.
    """
    try:
        value = int(value)
        if value < 0:
            raise TypeError()
        return value
    except TypeError:
        raise argparse.ArgumentTypeError("Invalid value.")


def _str() -> str:
    """Generate a random string."""
    return str(uuid.uuid4())


def generate_file(args: argparse.Namespace):
    """Generate a random JSON file.

    :param args: Command line arguments.
    """
    object_id = _str()
    obj = {
        "object_id": object_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "data": {
            _str(): (
                _str()
                if random.random() > 0.75
                else {_str(): _str() for __ in range(random.randint(1, 20))}
            )
            for _ in range(random.randint(1, 20))
        },
    }
    os.makedirs(args.target_directory, exist_ok=True)
    prefix = "array" if args.as_array else "object"
    filename = "{}_{}.json".format(prefix, object_id)
    path = os.path.join(args.target_directory, filename)
    with open(path, "w") as json_file:
        json.dump(
            [obj] if args.as_array else obj,
            json_file,
            indent=args.indent if args.indent else None,
        )
    print("  Done:", path)


def main():
    """Generate random JSON files."""
    args = _parse_args()
    for count in range(1, args.number + 1):
        print("Generating file {}...".format(count))
        generate_file(args)
        if count != args.number and args.delay:
            print("Waiting %s seconds..." % args.delay)
            time.sleep(args.delay)
    print("Done generating {} files.".format(args.number))


if __name__ == "__main__":
    main()
