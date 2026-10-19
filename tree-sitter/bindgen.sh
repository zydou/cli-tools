#!/usr/bin/env bash
# Disable rquickjs's `bindgen` feature in crates/generate/Cargo.toml.
#
# tree-sitter >= 0.26 enables rquickjs with the `bindgen` feature, which runs
# bindgen + libclang at build time to regenerate QuickJS's FFI bindings.
# bindgen >= 0.71 requires clang >= 9, but the cross-rs images used for the
# Linux targets ship older libclang (3.8 on x86_64/aarch64 -gnu, 6.0 on
# aarch64 -musl) that lacks clang_getTranslationUnitTargetInfo, so those three
# targets fail. The macOS targets build natively, where rquickjs-sys already
# reuses its bundled bindings because target == host.
#
# Dropping the feature makes rquickjs-sys fall back to its bundled,
# pre-generated bindings, which cover every triple we build:
#   x86_64/aarch64 - unknown-linux-gnu, unknown-linux-musl, apple-darwin
#
# This is a text transform rather than a `git apply` patch because upstream
# reflows this one dependency line between releases (one feature per line in
# v0.26.x and v0.27.x, everything on a single line on current HEAD) and bumps
# the rquickjs version every cycle. A patch has already had to be regenerated
# twice for exactly that reason (33ec70f, efdb6cd). The transform below does
# not depend on the array's line layout, key order or the rquickjs version.
set -euo pipefail

spec=crates/generate/Cargo.toml

if [ ! -f "$spec" ]; then
  echo "Skipping: ${spec} not found (pre-0.26 tree-sitter has no rquickjs dep)"
  exit 0
fi

# `bindgen` must occur exactly once: the rquickjs feature entry. Erroring out
# instead of blindly editing keeps this safe if upstream ever adds a second
# mention of bindgen elsewhere in the file.
count=$(perl -0ne '$c += s/["\x27]bindgen["\x27]//g; print $c' "$spec")
if [ "$count" -eq 0 ]; then
  echo "Skipping: ${spec} does not enable the bindgen feature"
  exit 0
fi
if [ "$count" -ne 1 ]; then
  echo "::error::expected exactly 1 bindgen entry in ${spec}, found ${count}. Update this script."
  exit 1
fi

# Drop the entry. Consuming the whitespace around the token keeps the result
# valid TOML whether the features array is one entry per line or all on one
# line, and whether bindgen is last (no trailing comma).
perl -0pi -e 's/\s*["\x27]bindgen["\x27],?\s*/ /g' "$spec"

if grep -q 'bindgen' "$spec"; then
  echo "::error::bindgen still present in ${spec} after removal. Update this script."
  exit 1
fi

echo "Disabled rquickjs's bindgen feature in ${spec}:"
grep -A6 -B1 '^rquickjs' "$spec" | sed 's/^/    /'
