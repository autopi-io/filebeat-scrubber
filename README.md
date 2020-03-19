# Filebeat Scrubber

Filebeat Scrubber performs operations on files that Filebeat has fully
harvested.

Currently, Filebeat Scrubber supports:

- Moving files to a custom destination directory.
- Permanently deleting files in place.

To do this, Filebeat Scrubber reads the Filebeat registry file for a list of 
all files that Filebeat has knowledge of. If a file has been fully harvested by 
Filebeat (i.e. bytes read = file size), it performs one of the actions listed
above.

Since this application depends on the registry file containing accurate
information, be sure to configure [registry flushing](
https://www.elastic.co/guide/en/beats/filebeat/current/configuration-general-options.html#_registry_flush
) for best results in your use case.

There is a fair bit of nuance when it comes to how Filebeat handles harvesting
files that are being moved or deleted. Be sure to read and understand the 
[close_*](
https://www.elastic.co/guide/en/beats/filebeat/current/filebeat-input-log.html#filebeat-input-log-close-options
) options and the [clean_*](
https://www.elastic.co/guide/en/beats/filebeat/current/filebeat-input-log.html#filebeat-input-log-clean-options
) options.

This README only serves as a simple guide and is in no way comprehensive. 
Official documentation from Filebeat supersedes this documentation. Any errors
or omissions should be reported so they can be corrected.

# Background

A common use case for logging is to write a file once (e.g. an event in JSON 
format) and never append to it again. Filebeat does not natively support 
deleting files that have been fully harvested. Therefore, a solution is needed 
to move or delete files once they have been fully harvested by Filebeat so that
the system does not run out of inodes or disk space.

[This use case has been discussed on the Beats Github page](
https://github.com/elastic/beats/issues/714
). In that discussion, a user suggested creating a custom solution that uses
the data from the Filebeat registry file. And in fact, [a user did just that
in Ruby](https://github.com/andrea-romagnoli/filebeat-cleaner).
Filebeat Scrubber, written in Python, was inspired by that project and the 
discussions in that thread.

Note that [Filebeat uses a newline character to detect the end of an event](
https://www.elastic.co/guide/en/beats/filebeat/master/newline-character-required-eof.html
). When writing a JSON file to disk, you must ensure that it ends with a 
newline or else Filebeat will not read the last line in the file. If you do
not terminate the line with a newline, it could lead to data loss and malformed
JSON.

# Installation

Before you proceed, it is recommended you setup a [virtual environment](
https://virtualenvwrapper.readthedocs.io/en/latest/).

Filebeat Scrubber is available from PyPI:

```shell script
pip install filebeat-scrubber
```

# Usage

```
$ filebeat_scrubber --help

usage: filebeat_scrubber [-h] [--registry-file REGISTRY_FILE]
                         [--destination TARGET_DIRECTORY] [--move] [--remove]
                         [--verbose] [--summary] [--input-type TYPE]
                         [--file-filter FILTER_REGEX] [--older-than AGE]

Process fully harvested files from Filebeat input paths.

optional arguments:
  -h, --help            show this help message and exit
  --registry-file REGISTRY_FILE
                        Full path to the Filebeat registry file. Default:
                        "/var/lib/filebeat/registry"
  --destination TARGET_DIRECTORY
                        Directory to move fully harvested files to.
  --move                Move the fully harvested files.
  --remove              Remove (delete) the fully harvested files.
  --verbose             Verbose output logging.
  --summary             Print summary of I/O operations.
  --input-type TYPE     Filebeat input "type" to filter fully harvested files
                        on. This argument can be provided multiple times.
  --file-filter FILTER_REGEX
                        Regex to filter fully harvested files with. The filter
                        is applied to the full path of the file. This argument
                        can be provided multiple times.
  --older-than AGE      The minimum age required, in seconds, since the
                        Filebeat harvester last processed a file before it can
                        be scrubbed.

NOTE: This script must be run as a user that has permissions to access the
Filebeat registry file and any input paths that are configured in Filebeat.
```

# Example

This example demonstrates handling multi-line JSON files that are only written
once and not updated from time to time.

## Filebeat Input Configuration

This configuration assumes that you have multi-line JSON files, and have 
separated files which are single objects into one naming scheme, and arrays of
objects into another scheme. If you only have one type, customize this
configuration as you see fit. This is provided purely as an example using
Filebeat 6. Your configuration will probably need to be different.

```yaml
filebeat.registry_flush: 5s

filebeat.inputs:

- type: log
  paths:
    - tests/json_files/object_*.json
  close_removed: true
  clean_removed: true
  multiline.pattern: ^\{
  multiline.negate: true
  multiline.match: after
  multiline.timeout: 5s

- type: log
  paths:
    - tests/json_files/array_*.json
  close_removed: true
  clean_removed: true
  multiline.pattern: ^\[
  multiline.negate: true
  multiline.match: after
  multiline.timeout: 5s
```

Using a `registry_flush` of 5 seconds ensures that the registry file is updated
on a regular interval instead of every time events are published. If you are
publishing a lot of events, using an interval can improve Filebeat performance
at the expense of registry accuracy. Configure this for your use case and needs.

Using `close_removed` tells Filebeat to close the harvester for a file when the
file is removed (moved or deleted). This is on by default, but set explicitly
here for clarity. Another option is using `close_eof`, which tells Filebeat to 
close a file once the harvester has reached the end of the file. This option
can lead to data loss if files are not written atomically (the harvester may
reach the end of the file before all of the data has been written to it).

Using `clean_removed` tells Filebeat to clean a file entry from the registry
if the file cannot be found on disk anymore under the last known name. This
prevents the Filebeat registry from becoming cluttered with data on files that
have been removed and that will never return. This is on by default, but set
explicitly here for clarity.

Using `multiline.*` settings accounts for the JSON being in multi-line (pretty-
printed/indented) format. If your JSON is on a single line, these settings 
should not be necessary. It is also possible to reverse these settings, and 
instead have `multiline.match: before` with `multiline.pattern: ^\]` or
`multiline.pattern: ^\}`. With these settings, it should not rely on the
`multiline.timeout` to trigger the event publishing, assuming all of the data
is available in the file at the time the harvester reads it. Using atomic
writes can ensure this.

## Filebeat Scrubber Command

**IMPORTANT** If your Filebeat is configured to also process regular appending
log files, it is important to add filters to Filebeat Scrubber so that it does
not operate on files you do not intend it to. **If you do not do this, you may 
experience data loss!**

### Moving Harvested Files

Example of moving fully harvested files to a separate directory.

```shell script
filebeat_scrubber \
    --move \
    --destination /tmp/fb-scrubber \
    --input-type log \
    --file-filter \.json$
```

If you want to delete these files at a later time, the following command will
delete any files older than 1 day:

```
$ find /tmp/fb-scrubber -type f -ctime +1 -delete
```

### Deleting Harvested Files in Place

Example of deleting fully harvested files in place.

```shell script
filebeat_scrubber \
    --remove \
    --input-type log \
    --file-filter \.json$
```

# Development

This project uses [tox](https://tox.readthedocs.io/en/latest/).

Grab the source code and setup your development environment using a [virtual 
environment](https://virtualenvwrapper.readthedocs.io/en/latest/):

```shell script
git clone git@github.com:barqshasbite/filebeat-scrubber.git
cd filebeat-scrubber
mkvirtualenv -p python3 filebeat-scrubber
pip install -r requirements.txt
```

Then build the project:

```shell script
tox
```

This will run static code analysis, tests, and packaging. Built packages can be
found in `dist/`. An HTML report of test coverage can be found in 
`reports/htmlcov/index.html`.

## Publishing a release to PyPI

Update the version of the release in `setup.py`.

Build the latest version of the project:

```shell script
tox
```

Publish the release with `twine`:

```shell script
twine upload dist/filebeat_scrubber-X.Y.Z-py3-none-any.whl
```

## End to End Testing

Install the current source code of Filebeat Scubber into your [virtual
environment](https://virtualenvwrapper.readthedocs.io/en/latest/):

```shell script
python setup.py install
```

Make sure you have [Filebeat installed](
https://www.elastic.co/guide/en/beats/filebeat/current/filebeat-installation.html
). E.g.:

```shell script
sudo apt-get install filebeat
```

Start a local Filebeat instance using the provided test config file:

```shell script
filebeat \
    -e \
    -c filebeat.yml \
    --path.config tests/config_files/ \
    --path.data tests/sandbox/
```

Start the JSON file generator to automatically create JSON files in the test
directory:

```shell script
python tests/tools/generate_json_files.py \
    --number 1000 \
    --delay 10 \
    --indent 4 \
    --file-prefix object_ \
    --destination tests/json_files
```

Start the Filebeat Scrubber to inspect which files can be scrubbed:

```shell script
watch filebeat_scrubber \
    --registry-file tests/sandbox/registry \
    --verbose \
    --summary \
    --input-type log \
    --file-filter object_.*\.json
```

Since `--move` and `--remove` are not provided, no action will be performed
and only information about what would happen is printed to the console.

Add `--move` or `--remove` if you wish to test the operations for real. 

That should be enough to see Filebeat Scrubber working. You can optionally go
a step further and see how Logstash would parse such a log. If you do not have 
Logstash installed, please do so:

```shell script
sudo apt-get install logstash
``` 

Edit the Filebeat configuration to enable outputting to Logstash. The sample
Filebeat configuration has a commented section for this. Comment out the
output configuration for `console` and uncomment the `logstash` configuration.

Run Logstash with the provided sample Logstash configuration:

```
/usr/share/logstash/bin/logstash \
    --path.config tests/config_files/logstash.conf \
    --path.data tests/sandbox \
    --log.level info
```

You should now see any messages posted from Filebeat to Logstash in your
console. Make sure that there are no JSON parsing errors.

### Cleanup

Delete files that were created from the testing:

```shell script
rm -rf tests/json_files tests/sandbox
``` 
