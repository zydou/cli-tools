#!/usr/bin/env bash
# Apply vendored-curl.patch.
#
# mdcat's `curl = "0.4.47"` declaration activates the curl crate's default
# `ssl` feature, which pulls openssl-sys and needs the host's libssl-dev
# headers. cross-rs Linux images don't ship dev headers, so the build fails on
# every Linux target. The patch drops the default feature and uses
# static-curl + static-ssl + zlib-ng, which vendors libcurl, OpenSSL and zlib
# into the binary. macOS still works because curl-sys auto-activates
# force-system-lib-on-osx on darwin.
set -euo pipefail

if ! git apply --check ../mdcat/vendored-curl.patch; then
  echo "::error::mdcat/vendored-curl.patch does not apply — upstream Cargo.toml's curl dep line changed. Re-generate the patch or drop it."
  exit 1
fi
git apply ../mdcat/vendored-curl.patch
