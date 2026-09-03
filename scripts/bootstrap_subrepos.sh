#!/usr/bin/env bash
# Bootstrap the 16 per-tool sub-repos under zydou/<tool>-binary.
#
# Reads build.json, creates each sub-repo (idempotent: skips if it
# already exists), seeds it with README.md (and .goreleaser.yaml for
# gopls) and a minimal clean-up.yml. Requires `gh` authenticated as
# the user that owns the zydou org.
#
# Usage:
#   ./scripts/bootstrap_subrepos.sh                # bootstrap all enabled tools
#   ./scripts/bootstrap_subrepos.sh mdcat gopls    # bootstrap specific tools
#
# Requires: gh (GitHub CLI) authenticated, jq, python3.

set -euo pipefail

cd "$(dirname "$0")/.."

# tools given as args, or all enabled in build.json
if [ "$#" -gt 0 ]; then
    TOOLS=("$@")
else
    mapfile -t TOOLS < <(python3 -c "
import json
d = json.load(open('build.json'))
for k, v in d.items():
    if not str(v.get('disabled', '')).lower() in ['1', 'true']:
        print(k)
")
fi

# short blurb per tool, for `gh repo create --description`
declare -A DESC=(
    [bore]="Nightly cross-compiled builds of bore"
    [delta]="Nightly cross-compiled builds of delta"
    [dua]="Nightly cross-compiled builds of dua"
    [gopls]="Nightly cross-compiled builds of gopls"
    [igrep]="Nightly cross-compiled builds of igrep"
    [macchina]="Nightly cross-compiled builds of macchina"
    [mdcat]="Nightly cross-compiled builds of mdcat"
    [onefetch]="Nightly cross-compiled builds of onefetch"
    [repgrep]="Nightly cross-compiled builds of repgrep"
    [rust-analyzer]="Nightly cross-compiled builds of rust-analyzer"
    [ryl]="Nightly cross-compiled builds of ryl"
    [taplo]="Nightly cross-compiled builds of taplo"
    [telemt]="Nightly cross-compiled builds of telemt"
    [texlab]="Nightly cross-compiled builds of texlab"
    [tokei]="Nightly cross-compiled builds of tokei"
    [tree-sitter]="Nightly cross-compiled builds of tree-sitter"
)

for tool in "${TOOLS[@]}"; do
    sub="zydou/${tool}-binary"
    echo "==> ${sub}"

    # 1. ensure repo exists (skip if already there)
    if ! gh repo view "$sub" >/dev/null 2>&1; then
        gh repo create "$sub" \
            --public \
            --description "${DESC[$tool]:-Nightly cross-compiled builds of $tool}" \
            --homepage "https://github.com/zydou/cli-tools" \
            >/dev/null
        echo "    created"
    else
        echo "    exists, skipping create"
    fi

    # 2. seed content in a temp dir
    work="$(mktemp -d)"
    trap "rm -rf '$work'" EXIT
    gh repo clone "$sub" "$work/repo" -- --depth=1 >/dev/null 2>&1 || {
        # fresh repo has no commits; init manually
        mkdir -p "$work/repo"
        (cd "$work/repo" && git init -q -b main && git remote add origin "https://github.com/${sub}.git")
    }

    # README.md
    if [ -f "${tool}/README.md" ]; then
        cp "${tool}/README.md" "$work/repo/README.md"
    else
        printf '# %s-binary\n\nNightly cross-compiled builds of [%s](%s).\n' \
            "$tool" "$tool" "https://github.com/zydou/cli-tools" \
            > "$work/repo/README.md"
    fi

    # gopls: copy .goreleaser.yaml too
    if [ "$tool" = "gopls" ] && [ -f "gopls/.goreleaser.yaml" ]; then
        cp "gopls/.goreleaser.yaml" "$work/repo/.goreleaser.yaml"
    fi

    # minimal clean-up.yml so each sub-repo self-cleans its own CI history
    mkdir -p "$work/repo/.github/workflows"
    cat > "$work/repo/.github/workflows/clean-up.yml" <<'YAML'
---
name: Weekly Cleanup
on:
  schedule:
    - cron: 42 13 * * 3
permissions: write-all
jobs:
  delete:
    runs-on: ubuntu-latest
    steps:
      - name: Delete old workflow runs
        uses: Mattraks/delete-workflow-runs@v2
        with:
          retain_days: 0
          keep_minimum_runs: 3
YAML

    # 3. commit and push (skip if no changes)
    (cd "$work/repo" && git add -A)
    if (cd "$work/repo" && git diff --cached --quiet); then
        echo "    no changes to push"
    else
        (cd "$work/repo" && \
            git -c user.email="ci@zydou.me" -c user.name="bootstrap" \
            commit -m "bootstrap: README + clean-up workflow" --quiet)
        (cd "$work/repo" && git push -u origin main --quiet 2>&1 | tail -1) || {
            # default branch might be master on freshly created repos
            (cd "$work/repo" && git push -u origin master --quiet 2>&1 | tail -1)
        }
        echo "    pushed"
    fi
done

echo "done."
