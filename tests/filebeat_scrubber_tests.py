# coding=utf-8

"""Filebeat Scrubber tests."""

import datetime
import logging
from argparse import Namespace, ArgumentTypeError
from unittest import TestCase
from unittest.mock import patch

from filebeat_scrubber import filebeat_scrubber


class BaseTestCase(TestCase):
    """Common base test class."""

    @classmethod
    def setUpClass(cls) -> None:
        filebeat_scrubber.LOGGER.setLevel(logging.ERROR)  # Shh...


class FilebeatScrubberTests(BaseTestCase):
    """Test core methods of the Filebeat Scrubber."""

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.info')
    def test_print_args_summary(self, mock_info):
        """Argument summary should print without issue."""
        args = Namespace(arg1=False, arg2="some string", arg3=123)
        filebeat_scrubber._print_args_summary(args)
        self.assertEqual(mock_info.call_count, 4)  # header + 3 args

    def test_init_stats(self):
        """A stats data structure should be returned."""
        stats = filebeat_scrubber._init_stats()
        self.assertEqual(stats, {
            'count_scrubbed': 0,
            'count_not_found': 0,
            'count_partial': 0,
        })

    def test_get_utc_now(self):
        """Should be able to get the current time in UTC."""
        now = filebeat_scrubber._get_utc_now()
        self.assertTrue(isinstance(now, datetime.datetime))
        self.assertAlmostEqual(now, datetime.datetime.utcnow(),
                               delta=datetime.timedelta(seconds=10))

    @patch('filebeat_scrubber.filebeat_scrubber._get_utc_now')
    def test_get_age(self, mock_utc_now):
        """Age of a source file should be retrievable."""
        mock_utc_now.return_value = datetime.datetime(2019, 12, 11, 19, 0, 0, 0)
        age = filebeat_scrubber._get_age('2019-12-11T18:55:00.000000Z')
        self.assertEqual(age, 300)
        age = filebeat_scrubber._get_age('2019-12-11T18:50:00.000000Z')
        self.assertEqual(age, 600)

    @patch('filebeat_scrubber.filebeat_scrubber._get_age')
    def test_read_registry_file(self, mock_get_age):
        """A registry file should be readable as JSON."""
        registry_1 = [{
            "timestamp": '2019-12-11T19:00:00.000000Z',
            "type": "type_1",
            "source": "log_1.txt",
            "offset": 123
        }, {
            "timestamp": '2019-12-11T19:30:00.000000Z',
            "type": "type_2",
            "source": "log_2.txt",
            "offset": 321
        }]
        args = Namespace(
            registry_file='tests/registry_files/registry_1.json',
            type=[],
            age=0,
            filter_regex=None)

        # Read data as-is.
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, registry_1)

        # Apply type filtering.
        args.type = ['type_1']
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, [registry_1[0]])
        args.type = ['type_2']
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, [registry_1[1]])

        # Apply regex filtering.
        args.type = ['type_1']
        test_regexes = [
            '^log_1.txt$',
            'log_1.txt',
            'log_1.*',
            'log_1',
            '^log_1',
            '.txt$',
        ]
        for test_regex in test_regexes:
            args.filter_regex = [test_regex]
            data = filebeat_scrubber._read_registry_file(args)
            self.assertEqual(data, [registry_1[0]])
        args.filter_regex = test_regexes
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, [registry_1[0]])
        args.type = []
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, registry_1)

        # Apply age filtering.
        mock_get_age.return_value = 50
        args.age = 100
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, [])
        args.age = 25
        data = filebeat_scrubber._read_registry_file(args)
        self.assertEqual(data, registry_1)

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.warning')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.getsize')
    def test_get_file_size(self, mock_getsize, mock_logger):
        """The size of a file should be returned."""
        mock_size = 100
        mock_getsize.return_value = mock_size
        size = filebeat_scrubber._get_file_size({}, {}, {'source': ""})
        self.assertEqual(mock_size, size)

        mock_getsize.side_effect = OSError()
        args = Namespace(verbose=False, show_summary=False)
        stats = filebeat_scrubber._init_stats()
        size = filebeat_scrubber._get_file_size(args, stats, {'source': ""})
        self.assertIsNone(size)
        self.assertEqual(0, stats['count_not_found'])
        self.assertFalse(mock_logger.called)

        args = Namespace(verbose=True, show_summary=True)
        size = filebeat_scrubber._get_file_size(args, stats, {'source': ""})
        self.assertIsNone(size)
        self.assertEqual(1, stats['count_not_found'])
        self.assertTrue(mock_logger.called)

    def test_print_summary(self):
        """Summary should print without issues."""
        args = Namespace(move=False, delete=False)
        stats = filebeat_scrubber._init_stats()
        filebeat_scrubber._print_summary(args, stats)

        args = Namespace(move=True, delete=False)
        filebeat_scrubber._print_summary(args, stats)

        args = Namespace(move=False, delete=True)
        filebeat_scrubber._print_summary(args, stats)

        stats['count_partial'] = 100
        self.assertIsNone(filebeat_scrubber._print_summary(args, stats))

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.info')
    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.exception')
    @patch('filebeat_scrubber.filebeat_scrubber.shutil.move')
    @patch('filebeat_scrubber.filebeat_scrubber.os.makedirs')
    def test_move_file(self, mock_makedirs, mock_move, mock_exc, mock_info):
        """Files should be moved to target directory."""
        args = Namespace(verbose=False, target_directory='mocked target dir')
        source_file = 'mocked source file'

        filebeat_scrubber._move_file(args, source_file)
        self.assertTrue(mock_makedirs.called)
        self.assertFalse(mock_exc.called)
        self.assertTrue(mock_move.called)
        self.assertFalse(mock_info.called)

        args.verbose = True
        filebeat_scrubber._move_file(args, source_file)
        self.assertTrue(mock_info.called)
        mock_info.reset_mock()

        mock_move.side_effect = OSError()
        filebeat_scrubber._move_file(args, source_file)
        self.assertTrue(mock_exc.called)
        self.assertFalse(mock_info.called)

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.info')
    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.exception')
    @patch('filebeat_scrubber.filebeat_scrubber.os.remove')
    def test_delete_file(self, mock_remove, mock_exc, mock_info):
        """Files should be deleted."""
        args = Namespace(verbose=False)
        source_file = 'mocked source file'

        filebeat_scrubber._delete_file(args, source_file)
        self.assertTrue(mock_remove.called)
        self.assertFalse(mock_exc.called)
        self.assertFalse(mock_info.called)

        args.verbose = True
        filebeat_scrubber._delete_file(args, source_file)
        self.assertTrue(mock_info.called)
        mock_info.reset_mock()

        mock_remove.side_effect = OSError()
        filebeat_scrubber._delete_file(args, source_file)
        self.assertTrue(mock_exc.called)
        self.assertFalse(mock_info.called)

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.info')
    def test_partial_read_stats(self, mock_info):
        """Stats should be collected for partial reads."""
        args = Namespace(verbose=False, show_summary=False)
        stats = filebeat_scrubber._init_stats()
        input_data = {
            'source': 'mocked source',
            'offset': 10,
            'source_size': 100
        }
        filebeat_scrubber._partial_read_stats(args, stats, input_data)
        self.assertFalse(mock_info.called)
        self.assertEqual(stats['count_partial'], 0)

        args.verbose = True
        filebeat_scrubber._partial_read_stats(args, stats, input_data)
        self.assertTrue(mock_info.called)

        args.show_summary = True
        for value in range(10):
            input_data['offset'] = value * 10
            filebeat_scrubber._partial_read_stats(args, stats, input_data)
        self.assertEqual(stats['count_partial'], 10)

    def test_increment_scrubbed(self):
        """Counter should increase by one each time."""
        stats = {'count_scrubbed': 0}
        filebeat_scrubber._increment_scrubbed(stats)
        self.assertEqual(stats['count_scrubbed'], 1)
        filebeat_scrubber._increment_scrubbed(stats)
        self.assertEqual(stats['count_scrubbed'], 2)
        filebeat_scrubber._increment_scrubbed(stats)
        self.assertEqual(stats['count_scrubbed'], 3)

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.error')
    def test_parse_args(self, _):
        """Filebeat Scrubber should parse and validate arguments."""
        filebeat_scrubber._parse_args([])
        with self.assertRaises(SystemExit):
            filebeat_scrubber._parse_args(['--move', '--remove'])

    def test_regex(self):
        """Regex text should be validated."""
        filebeat_scrubber._regex("^valid$")
        with self.assertRaises(ArgumentTypeError):
            filebeat_scrubber._regex("^(invalid$")


class FilebeatScrubberMainTests(BaseTestCase):
    """Test the main method of the Filebeat Scrubber."""

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.fatal')
    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._print_args_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._init_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_1(self, mock_args, mock_stats, mock_args_sum, mock_exists,
                    mock_registry, mock_size, mock_move, mock_delete,
                    mock_partial, mock_summary, mock_fatal):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=False,
            verbose=False,
            registry_file=False,
            show_summary=False,
        )
        mock_exists.return_value = False
        filebeat_scrubber.main()
        self.assertTrue(mock_args.called)
        self.assertTrue(mock_stats.called)
        self.assertFalse(mock_args_sum.called)
        self.assertTrue(mock_exists.called)
        self.assertFalse(mock_registry.called)
        self.assertFalse(mock_size.called)
        self.assertFalse(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertFalse(mock_summary.called)
        self.assertTrue(mock_fatal.called)

    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.fatal')
    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_2(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary,
                    mock_fatal):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=False,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = False
        filebeat_scrubber.main()
        self.assertFalse(mock_registry.called)
        self.assertFalse(mock_size.called)
        self.assertFalse(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertTrue(mock_summary.called)
        self.assertTrue(mock_fatal.called)

    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_3(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=False,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = True
        mock_registry.return_value = [{
            'offset': 100,
            'source': 'mocked source'
        }]
        mock_size.return_value = None
        filebeat_scrubber.main()
        self.assertTrue(mock_registry.called)
        self.assertTrue(mock_size.called)
        self.assertFalse(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertTrue(mock_summary.called)

    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_4(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=False,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = True
        mock_registry.return_value = [{
            'offset': 100,
            'source': 'mocked source'
        }]
        mock_size.return_value = 99
        filebeat_scrubber.main()
        self.assertFalse(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertTrue(mock_partial.called)
        self.assertTrue(mock_summary.called)
        mock_partial.reset_mock()

    @patch('filebeat_scrubber.filebeat_scrubber._increment_scrubbed')
    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_5(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary,
                    mock_increment):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=True,
            delete=False,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = True
        mock_registry.return_value = [{
            'offset': 99,
            'source': 'mocked source'
        }]
        mock_size.return_value = 100
        filebeat_scrubber.main()
        self.assertTrue(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertTrue(mock_summary.called)
        self.assertTrue(mock_increment.called)
        mock_move.reset_mock()

    @patch('filebeat_scrubber.filebeat_scrubber._increment_scrubbed')
    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_6(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary,
                    mock_increment):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=True,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = True
        mock_registry.return_value = [{
            'offset': 99,
            'source': 'mocked source'
        }]
        mock_size.return_value = 100
        filebeat_scrubber.main()
        self.assertFalse(mock_move.called)
        self.assertTrue(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertTrue(mock_summary.called)
        self.assertTrue(mock_increment.called)
        mock_delete.reset_mock()

    @patch('filebeat_scrubber.filebeat_scrubber._increment_scrubbed')
    @patch('filebeat_scrubber.filebeat_scrubber.LOGGER.info')
    @patch('filebeat_scrubber.filebeat_scrubber._print_summary')
    @patch('filebeat_scrubber.filebeat_scrubber._partial_read_stats')
    @patch('filebeat_scrubber.filebeat_scrubber._delete_file')
    @patch('filebeat_scrubber.filebeat_scrubber._move_file')
    @patch('filebeat_scrubber.filebeat_scrubber._get_file_size')
    @patch('filebeat_scrubber.filebeat_scrubber._read_registry_file')
    @patch('filebeat_scrubber.filebeat_scrubber.os.path.exists')
    @patch('filebeat_scrubber.filebeat_scrubber._parse_args')
    def test_main_7(self, mock_args, mock_exists, mock_registry, mock_size,
                    mock_move, mock_delete, mock_partial, mock_summary,
                    mock_info, mock_increment):
        """Filebeat Scrubber should operate nominally."""
        mock_args.return_value = Namespace(
            move=False,
            delete=False,
            verbose=True,
            registry_file=False,
            show_summary=True,
        )
        mock_exists.return_value = True
        mock_registry.return_value = [{
            'offset': 99,
            'source': 'mocked source'
        }]
        mock_size.return_value = 100
        filebeat_scrubber.main()
        self.assertFalse(mock_move.called)
        self.assertFalse(mock_delete.called)
        self.assertFalse(mock_partial.called)
        self.assertTrue(mock_summary.called)
        self.assertTrue(mock_increment.called)
        self.assertTrue(mock_info.called)
