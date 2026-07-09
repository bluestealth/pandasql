#!/bin/bash

pandoc -f markdown -t rst README.md > README.rst
uv build
