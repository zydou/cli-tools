#!/usr/bin/env bash
# Apply symlink-target-size.patch.
#
# lsd's size column showed a symlink's own size (the byte length of the target
# path string) instead of the target's real size. The patch changes from_path
# so it reads the size from the target file's metadata (already fetched for
# file_type) rather than the link's.
set -euo pipefail

if ! git apply --check ../lsd/symlink-target-size.patch; then
  echo "::error::lsd/symlink-target-size.patch does not apply — upstream src/meta/mod.rs changed around the size computation. Re-generate the patch or drop it."
  exit 1
fi
git apply ../lsd/symlink-target-size.patch
