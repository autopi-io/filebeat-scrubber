# coding=utf-8

import setuptools

with open("README.md", "r") as readme_file:
    long_description = readme_file.read()

setuptools.setup(
    name="filebeat-scrubber",
    version="1.1.0",
    author="barqshasbite",
    description="Filebeat Scrubber performs operations on files that Filebeat "
                "has fully harvested.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/barqshasbite/filebeat-scrubber",
    packages=setuptools.find_packages(exclude=['tests*']),
    entry_points={
        'console_scripts': [
            'filebeat_scrubber = filebeat_scrubber.filebeat_scrubber:main',
        ],
    },
    setup_requires=[
        'wheel',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
)
