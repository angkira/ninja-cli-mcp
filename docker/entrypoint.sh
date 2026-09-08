#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
    set -- ninja-mcp --help
fi

case "$1" in
    ninja-mcp|ninja-coder|ninja-researcher|ninja-secretary|ninja-agent|ninja-daemon|ninja-config)
        exec "$@"
        ;;
    *)
        exec ninja-mcp "$@"
        ;;
esac
