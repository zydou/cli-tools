# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

`cli-tools` is a **nightly cross-compilation build farm** for popular third-party CLI tools.
It does not contain the tools' source code — instead it holds build configuration, per-tool patches, and GitHub Actions workflows that checkout upstream repos, cross-compile them for multiple targets,
and publish the resulting binaries as GitHub release assets under <https://github.com/zydou/cli-tools/releases>.

The repo is driven entirely by CI.
There is no local build/test loop — changes to `build.json` or the workflow files are validated by pushing to `main` and observing the resulting workflow runs.

## Architecture

### Build manifest: `build.json`

The single source of truth for what gets built.
Each key is a tool name with:

- `type`: `rust` (35 tools) or `golang` (4 tools)
- `upstream`: GitHub `org/repo` that gets checked out and built
- `bin`: output binary name (may differ from tool name, e.g. `igrep` → `ig`, `repgrep` → `rgr`)
- `build_args` (rust): extra `cargo build` flags (e.g. `-p taplo-cli --features lsp`, `--all-features`)
- `ldflags` / `goversion` (golang): Go build ldflags and minimum Go version
- `target_*`: booleans per target triple — controls which of the 6 targets get built
- `disabled`: set to `true` to skip a tool without removing its config (28 of 39 are currently disabled)

**Active (non-disabled) tools:** bore, delta, dua, igrep, macchina, onefetch, repgrep, taplo, texlab, tokei, tree-sitter.

### Scheduler: `scheduler.py`

Runs on a cron (`0 8 * * *`) via `.github/workflows/scheduler.yml`, and also on every push to `main` that touches `build.json`, `scheduler.py`, or the workflow file itself.
For each enabled tool it:

1. Queries the upstream repo's HEAD commit via GitHub API
2. Checks whether a release asset already exists for that commit (asset names embed the 7-char commit SHA)
3. Dispatches `build-rust` or `build-go` workflow runs only for missing target/commit combos

### Build workflows

- **`.github/workflows/build-rust.yml`** — checks out the upstream repo at the given ref, installs `rust-toolchain`, uses `cross` for cross-compilation (Linux targets) or native runners
  (macOS targets), builds with the configured `build_args`, then tars the single binary and calls `uploader.py`.
  Applies `hoard/openssl.patch` for the `hoard` tool.
- **`.github/workflows/build-go.yml`** — checks out upstream, installs Go + goreleaser, copies the tool's `.goreleaser.yaml` from its directory into the upstream tree,
  runs `goreleaser release --auto-snapshot --clean`, and uploads via `ncipollo/release-action`.
- **`.github/workflows/tmux.yml`** — special case: builds tmux from C source via Docker (musl + libevent + ncurses, compressed with UPX).
  Triggered manually with a version input.
- **`.github/workflows/clean-up.yml`** — weekly cleanup of old/failed/cancelled workflow runs.

### Uploader: `uploader.py`

Called at the end of `build-rust` jobs.
Handles deduplication (skips if asset exists), deletes old assets
(keeps those updated in the last day or with ≥2 downloads), uploads the new tarball, and edits the release body with the build timestamp and upstream commit link.
Release names match the tool name; assets are named `{tool}-{target}-{commit_sha_7}.tar.xz`.

### Per-tool directories

Each tool has a directory at the repo root.
Most contain only a `README.md` documenting the upstream repo, supported architectures, and download links.
A few carry build customization:

- `cheat/`, `cointop/`, `httpstat/`, `ticker/` — `.goreleaser.yaml` (Go tools)
- `hoard/` — `openssl.patch` (applied during rust build)
- `tmux/` — `Dockerfile` and `nightly.Dockerfile` (C build via Docker)

## Common tasks

### Add a new tool

1. Add an entry to `build.json` with the right `type`, `upstream`, `bin`, build flags, and target booleans.
2. Create a directory named after the tool with a `README.md` (follow the format in existing ones — upstream link, architecture list, release links).
3. For Go tools, add a `.goreleaser.yaml` in the tool directory (see `cheat/.goreleaser.yaml` for the format — `project_name` and `builds.[0].binary` get overwritten by the workflow).
4. For Rust tools needing patches, add a patch file and wire it into `build-rust.yml` (see the `hoard` openssl step).
5. Push to `main` — the scheduler will pick it up on the next run.

### Enable/disable a tool

Flip the `disabled` flag in `build.json`.
Disabled tools are skipped by the scheduler without losing their configuration.

### Trigger a manual build

Use **Actions → Build Rust / Build Go → Run workflow** on GitHub, supplying the tool's `build.json` values.
For tmux, use the tmux workflow with a version string.

### Test changes locally

There is no local build harness.
The Python scripts (`scheduler.py`, `uploader.py`) require `GITHUB_TOKEN` and `GITHUB_REPOSITORY` env vars and talk to the GitHub API.
The actual compilation happens inside GitHub Actions runners.
Validate by pushing to `main` and watching the workflow runs.

## Conventions

- Asset naming must stay consistent: `{tool}-{target}-{7-char-sha}.tar.xz` for rust, `{tool}-linux-amd64.tar.xz` for go.
  The scheduler and uploader both depend on these patterns.
- `build.json` keys are ordered alphabetically (maintained by convention).
- New macOS builds use `macos-latest` (Arm64) or `macos-15-intel` (Intel) as the runner; Linux targets use `ubuntu-latest` with `cross`.
- Rust release profile is hardened in `build-rust.yml`: `strip = true`, `opt-level = "z"`, `lto = true`, `codegen-units = 1`, `panic = "abort"`.
- **Binary name vs tool name**: the `bin` field can differ from the dict key.
  Notable mismatches: `igrep`→`ig`, `repgrep`→`rgr`, `skim`→`sk`, `tailspin`→`tspin`, `tealdeer`→`tldr`, `tlrc`→`tldr`.
  Both `tealdeer` and `tlrc` emit `tldr` — do not enable both at once.
- New tools normally only need `build.json` + a tool subdir; edit workflow YAML only for special cases (patches like `hoard/openssl.patch`, or custom builds like tmux).
- Repo history is shallow (a few squashed commits); active state lives in `build.json` + the workflow YAMLs, not in git history.

## Known quirks

- `uploader.py` ends `main()` with two identical `gh.edit_release()` calls — harmless, don't "fix" unless asked.
- Per-tool `README.md` files sometimes have consecutive duplicate link lines — they render correctly on GitHub.
- `build-go.yml` only produces `linux-amd64`; Go tools don't build darwin/other targets through this pipeline.
