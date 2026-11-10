#!/bin/env bash

python build.py && python3 -m http.server -d _site 8000
