#!/bin/sh

# Get to a predictable directory, the directory of this script
cd "$(dirname "$0")"

source /root/TLE/venv/bin/activate

[ -e secrets ] && . ./secrets

git pull
python -m pip install -r requirements.txt
FONTCONFIG_FILE=$PWD/extra/fonts.conf python __main__.py
