#!/usr/bin/env bash
# Apply http-proxy.patch.
#
# bore has no proxy support, so a client behind an egress-only network cannot
# reach a bore server. The patch adds `--proxy` / `BORE_PROXY`, which routes
# the client's control and data connections through an HTTP CONNECT proxy.
# Connections to the local service being forwarded are always direct. See the
# module docs in src/proxy.rs.
#
# The patch is functional source only (src/{lib,client,main,proxy}.rs) — no
# docs, no tests. It is a breaking change to Client::new(), which gains a
# `proxy` parameter, so the upstream e2e test call sites no longer compile.
# build-rust only runs `cargo build`, which never compiles tests/, so CI is
# unaffected.
set -euo pipefail

if ! git apply --check ../bore/http-proxy.patch; then
  echo "::error::bore/http-proxy.patch does not apply — upstream src/client.rs, src/main.rs or src/lib.rs drifted. Re-generate the patch or drop it."
  exit 1
fi
git apply ../bore/http-proxy.patch
