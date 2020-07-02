# coding=utf-8

"""Filebeat Scrubber."""

import argparse
import datetime
import json
import logging
import os
import re
import shutil
import sre_compile
import sys
import time
from typing import Dict, List, Optional


def _setup_logger() -> logging.Logger:
    """Setup logging."""
    log_format = '[%(asctime)s][%(levelname)s] %(message)s'
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(log_format))
    stream_handler.setLevel(logging.INFO)
    custom_logger = logging.getLogger(__name__)
    custom_logger.addHandler(stream_handler)
    custom_logger.setLevel(logging.INFO)
    custom_logger.propagate = False
    return custom_logger


LOGGER = _setup_logger()


def _parse_args(args) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Process fully harvested files from Filebeat input paths.',
        epilog='NOTE: This script must be run as a user that has permissions '
               'to access the Filebeat registry file and any input paths that '
               'are configured in Filebeat.')
    parser.add_argument(
        '--registry-file',
        type=str,
        dest="registry_file",
        default='/var/lib/filebeat/registry',
        help='Full path to the Filebeat registry file. '
             'Default: "/var/lib/filebeat/registry"')
    parser.add_argument(
        '--destination',
        type=str,
        dest="target_directory",
        required=False,
        help='Directory to move fully harvested files to.')
    parser.add_argument(
        '--move',
        action='store_true',
        dest="move",
        default=False,
        help='Move the fully harvested files.')
    parser.add_argument(
        '--remove',
        action='store_true',
        dest="delete",
        default=False,
        help='Remove (delete) the fully harvested files.')
    parser.add_argument(
        '--verbose',
        action='store_true',
        dest="verbose",
        default=False,
        help='Verbose output logging.')
    parser.add_argument(
        '--summary',
        action='store_true',
        dest="show_summary",
        default=False,
        help='Print summary of I/O operations.')
    parser.add_argument(
        '--input-type',
        action='append',
        dest="type",
        required=False,
        help='Filebeat input "type" to filter fully harvested files on. This '
             'argument can be provided multiple times.')
    parser.add_argument(
        '--file-filter',
        type=_regex,
        action='append',
        dest="filter_regex",
        required=False,
        help='Regex to filter fully harvested files with. The filter is '
             'applied to the full path of the file. This argument can be '
             'provided multiple times.')
    parser.add_argument(
        "--older-than",
        type=int,
        dest="age",
        default=0,
        help="The minimum age required, in seconds, since the Filebeat "
             "harvester last processed a file before it can be scrubbed.")
    parser.add_argument(
        "--interval",
        type=int,
        dest="interval",
        default=0,
        help="The interval to run Filebeat Scrubber with. If specified, "
             "Filebeat Scrubber will run indefinitely at the configured "
             "interval instead of running once and closing.")
    args = parser.parse_args(args)
    if args.move and args.delete:
        LOGGER.error('Files can be moved *or* deleted, not both.')
        sys.exit(1)
    return args


def _regex(value: str):
    """Check for valid regex.

    :param value: A regex pattern.
    :return: The compiled regex.
    """
    try:
        return re.compile(value)
    except sre_compile.error as error:
        raise argparse.ArgumentTypeError(
            'Invalid filter regex provided. %s' % error.msg)


def _print_args_summary(args: argparse.Namespace):
    """Print summary of command line arguments.

    :param args: Command line arguments.
    """
    LOGGER.info('Filebeat Scrubber running with arguments:')
    for name, value in sorted(args.__dict__.items()):
        LOGGER.info('  %s = %s', name, value)


def _init_stats() -> Dict:
    """Create a statistics data structure.

    :return: A new statistics data structure.
    """
    return {
        'count_scrubbed': 0,
        'count_not_found': 0,
        'count_partial': 0,
    }


def _get_utc_now() -> datetime.datetime:
    """Get the current time in UTC format."""
    return datetime.datetime.utcnow()


def _get_age(timestamp: str):
    """Get the elapsed time since the provided timestamp.

    :param timestamp: A timestamp in ISO 8601 format.
    :return: The amount of time elapsed, in seconds.
    """
    now = _get_utc_now()
    try:
        date_object = datetime.datetime.strptime(
            timestamp,
            "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # Truncate nanoseconds.
        date_object = datetime.datetime.strptime(
            timestamp[:-4],
            "%Y-%m-%dT%H:%M:%S.%f")
    return (now - date_object).total_seconds()


def _read_registry_file(args: argparse.Namespace) -> List[Dict]:
    """Read the contents of the registry JSON file.

    This also filters the contents of the registry file based on the provided
    command line arguments for '--input-type', '--file-filter', and
    '--older-than'.

    :param args: Parsed command line arguments.
    :return: Contents of the parsed and filtered registry JSON file.
    """
    with open(args.registry_file, 'r') as _registry_file:
        data = json.load(_registry_file)
    if args.type:
        data = [entry for entry in data if entry.get('type') in args.type]
    if args.age:
        data = [entry for entry in data
                if _get_age(entry['timestamp']) >= args.age]
    if args.filter_regex:
        filter_regexes = [re.compile(regex) for regex in args.filter_regex]
        data = [entry for entry in data if any(regex.search(entry['source'])
                                               for regex in filter_regexes)]
    return data


def _get_file_size(args, stats, input_data: Dict) -> Optional[int]:
    """Return the size of a file, in bytes.

    :param args: Parsed command line arguments.
    :param stats: Statistics data structure.
    :param input_data: Input data from registry for file.
    :return: Size of the file, in bytes. If not found, None is returned.
    """
    try:
        input_data['source_size'] = os.path.getsize(input_data['source'])
        return input_data['source_size']
    except OSError:
        if args.verbose:
            LOGGER.warning("File '%s' not found!", input_data['source'])
        if args.show_summary:
            stats['count_not_found'] += 1
        return None


def _print_summary(args: argparse.Namespace, stats: Dict):
    """Print a summary of what was done.

    :param args: Parsed command line arguments.
    :param stats: Statistics data structure.
    """
    LOGGER.info("Filebeat Scrubber Summary:")
    if args.move:
        LOGGER.info("  Moved files:             %s", stats['count_scrubbed'])
    elif args.delete:
        LOGGER.info("  Deleted files:           %s", stats['count_scrubbed'])
    else:
        LOGGER.info("  Scrubbable files:        %s", stats['count_scrubbed'])
    LOGGER.info("  Files not found:         %s", stats['count_not_found'])
    LOGGER.info("  Partially read files:    %s", stats['count_partial'])


def _move_file(args: argparse.Namespace, source_file: str):
    """Move a file to a new directory.

    :param args: Parsed command line arguments.
    :param source_file: Path of file to move.
    """
    move_ok = False
    try:
        os.makedirs(args.target_directory, exist_ok=True)
        shutil.move(source_file, args.target_directory)
        move_ok = True
    except OSError:
        LOGGER.exception('FAILED to move file: %s', source_file)
    if args.verbose and move_ok:
        LOGGER.info("MOVED: %s", source_file)


def _delete_file(args: argparse.Namespace, source_file: str):
    """Delete a file.

    :param args: Parsed command line arguments.
    :param source_file: Path of file to move.
    """
    delete_ok = False
    try:
        os.remove(source_file)
        delete_ok = True
    except OSError:
        LOGGER.exception('FAILED to delete file: %s', source_file)
    if args.verbose and delete_ok:
        LOGGER.info("DELETED: %s", source_file)


def _partial_read_stats(
        args: argparse.Namespace,
        stats: Dict,
        input_data: Dict,
):
    """Calculate statistics about partially read files.

    :param args: Parsed command line arguments.
    :param stats: Statistics data structure.
    :param input_data: Input data from registry for partially read file.
    """
    if args.verbose:
        percent = (input_data['offset'] / input_data['source_size']) * 100.0
        LOGGER.info("Partially read file (%0.2f%%): %s  [offset=%s, size=%s]",
                    percent, input_data['source'], input_data['offset'],
                    input_data['source_size'])
    if args.show_summary:
        stats['count_partial'] += 1


def _increment_scrubbed(stats):
    """Increment the number of scrubbed items.

    :param stats: Statistics data structure.
    """
    stats['count_scrubbed'] += 1


def scrub(args: argparse.Namespace, stats: Dict):
    """Scrub files form registry that are fully harvested.

    :param args: Command line arguments.
    :param stats: Stats dictionary.
    """
    if os.path.exists(args.registry_file):
        registry_data = _read_registry_file(args)
        for input_data in registry_data:
            source_size = _get_file_size(args, stats, input_data)
            if source_size is None:
                continue
            if input_data['offset'] == source_size:
                if args.move:
                    _move_file(args, input_data['source'])
                elif args.delete:
                    _delete_file(args, input_data['source'])
                elif args.verbose:
                    LOGGER.info("Fully read file (100%%): %s",
                                input_data['source'])
                if args.show_summary:
                    _increment_scrubbed(stats)
            else:
                _partial_read_stats(args, stats, input_data)
    else:
        LOGGER.fatal('Registry file missing. Filebeat may not have created it '
                     'yet, or you do not have permission to access it.')


def main():
    """Scrub fully harvested files."""
    args = _parse_args(sys.argv[1:])
    if args.verbose:
        _print_args_summary(args)
    stats = _init_stats()
    scrub(args, stats)
    if args.interval > 0:
        try:
            while True:
                time.sleep(args.interval)
                scrub(args, stats)
        except KeyboardInterrupt:
            pass
    if args.show_summary:
        _print_summary(args, stats)
