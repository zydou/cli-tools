#!/usr/bin/env bash
# Apply start-tab.patch.
#
# gitui's upstream has no --start-tab flag. The patch makes App::new open on the
# CLI-given tab index (0: Status, 1: Log, 2: Files, 3: Stashing, 4: Stashes)
# when given, falling back to the per-repo .git/gitui persisted tab. It also
# guards set_tab against an out-of-range index, since it is reached from
# Options::current_tab() which reads a user-editable .git/gitui.
set -euo pipefail

if ! git apply --check ../gitui/start-tab.patch; then
  echo "::error::gitui/start-tab.patch does not apply — upstream src/app.rs, src/args.rs or src/main.rs drifted. Re-generate the patch or drop it."
  exit 1
fi
git apply ../gitui/start-tab.patch
