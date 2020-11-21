#!/bin/sh

# Get to a predictable directory, the directory of this script
cd "$(dirname "$0")"

[ -e secrets ] && . ./secrets

while true; do
    git pull
    pip3 install -r requirements.txt
    FONTCONFIG_FILE=$PWD/extra/fonts.conf python3 __main__.py

    (( $? != 42 )) && break

    echo '==================================================================='
    echo '=                       Restarting                                ='
    echo '==================================================================='
done
