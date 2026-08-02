#!/bin/sh
set -eu
mkdir -p /data/uploads
mkdir -p /data/models
chown -R appuser:appuser /data/uploads /data/models
exec gosu appuser "$@"
