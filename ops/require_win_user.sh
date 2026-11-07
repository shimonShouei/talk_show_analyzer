#!/bin/bash
# Source before any /mnt/c/Users/${WIN_USER} path.
#
# The export bundler replaced the box path /mnt/c/Users/Administrator with
# ${WIN_USER}. If WIN_USER is unset, that expansion is empty and the path
# points at /mnt/c/Users/ itself. This script refuses that.
#
# Set it to the Windows account folder name only, not a path:
#   export WIN_USER=YourName
#
# Allowed characters: letters, digits, dot, underscore, hyphen.
# $HOME is unrelated. Do not clear $HOME; WSL scripts use it as the Linux home.

if [ -n "${TSA_WIN_USER_CHECKED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

if [ -z "${WIN_USER:-}" ]; then
  echo "WIN_USER is required. Export the Windows account folder name under /mnt/c/Users (example: export WIN_USER=YourName). Refusing to continue with it unset." >&2
  exit 1
fi
case "$WIN_USER" in
  ""|.*|*"/"*|*"\\"*)
    echo "WIN_USER must be a single account folder name, not a path." >&2
    exit 1
    ;;
esac
case "$WIN_USER" in
  *[!A-Za-z0-9._-]*)
    echo "WIN_USER contains characters that are not allowed. Use only the account folder name (letters, digits, dot, underscore, hyphen)." >&2
    exit 1
    ;;
esac

export TSA_WIN_USER_CHECKED=1
