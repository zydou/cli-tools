# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

`cli-tools` is a **nightly cross-compilation build farm** for popular third-party CLI tools.
It does not contain the tools' source code — instead it holds build configuration, per-tool patches, and GitHub Actions workflows that checkout upstream repos, cross-compile them for multiple targets, and publish the resulting binaries as GitHub release assets in a per-tool **sub-repo** (`zydou/<tool>-binary`).

The repo is driven entirely by CI.
There is no local build/test loop — changes to `build.json` or the workflow files are validated by pushing to `main` and observing the resulting workflow runs.

## Architecture

### Build manifest: `build.json`

The single source of truth for what gets built: **17 tools, all enabled** (16 `rust`, 1 `golang`). No tool is currently `disabled`.

Each key is a tool name with:

- `type`: `rust` or `golang`
- `upstream`: GitHub `org/repo` that gets checked out and built
- `repo`: **required for enabled tools** — the sub-repo that receives the releases. The scheduler skips any enabled tool that lacks it.
- `bin`: output binary name (may differ from tool name)
- `build_args` (rust): extra `cargo build` flags
- `ldflags` / `goversion` (golang): Go build ldflags and minimum Go version
- `target_*`: booleans per target triple. Every enabled rust tool builds all 6; the field is what controls it.
- `disabled`: set to `true` to skip a tool without removing its config. Still honored by `scheduler.py`, but unused as of now.

**Enabled tools:** bore, delta, dua, gopls, igrep, lessi, macchina, mdcat, onefetch, repgrep, rust-analyzer, ryl, taplo, telemt, texlab, tokei, tree-sitter.

### Scheduler: `scheduler.py`

Runs on a cron (`0 8 * * *`) via `.github/workflows/scheduler.yml`, and also on every push to `main` that touches `build.json`, `scheduler.py`, or the workflow file itself. For each enabled tool it:

1. Queries the upstream repo's HEAD commit via GitHub API.
2. **nightly** — parses the sub-repo's `nightly` release body into a per-target record of which upstream commit each target was built from (written by `uploader.py`; asset filenames carry no commit hash). Dispatches builds only for targets whose recorded commit differs from HEAD, with `ref=HEAD` and `release=nightly`.
3. **tag** — normalizes every upstream tag through the `TAG_RULES` table, keeps the highest semver, and dispatches the missing per-target assets with `ref=tag_sha` and `release=normalized_name`.

`TAG_RULES` holds one entry per non-standard tag scheme — `mdcat` (`mdcat-1.2.3` → `v1.2.3`), `rust-analyzer` (`2026-09-04` → `2026-09-04`), `taplo` (bare `1.2.3` → `v1.2.3`), `gopls` (`gopls/v0.23.0` → `v0.23.0`) — plus a `_default` rule (`v?(\d+\.\d+\.\d+)` → `v1.2.3`). A tool tagged `v1.2.3` needs no entry.

### Build workflows

- **`.github/workflows/build-rust.yml`** — checks out the upstream repo at the given ref, installs `rust-toolchain`, builds with the configured `build_args`, then tars the single binary and calls `uploader.py`. Linux targets run on `ubuntu-latest` under a pre-downloaded `cross` binary (`v0.2.5` — downloaded instead of `cargo install`ed, to skip ~5 min of compile time); macOS targets run natively on `macos-15-intel` (Intel) or `macos-latest` (Arm64).
- **`.github/workflows/build-go.yml`** — checks out upstream, installs Go + goreleaser, copies the tool's `.goreleaser.yaml` from its directory into the upstream tree (overwriting `project_name`, `builds.[0].binary` and `builds.[0].ldflags` with `dasel`), runs `goreleaser release --auto-snapshot --clean`, and uploads each archive via `uploader.py`. Go cross-compiles natively, so a single run produces all 4 targets.
- **`.github/workflows/clean-up.yml`** — weekly cleanup of old/failed/cancelled workflow runs.

Uploads use `secrets.PAT` rather than the default `GITHUB_TOKEN`: the upload target is a different user-owned repo and the default token gets 403 on cross-repo writes.

### Uploader: `uploader.py`

Called at the end of every build job. Uploads the tarball with `--clobber` (replacing same-named assets, never deleting others) and updates the release body's per-target record line. Releases are named after the release: `nightly` is created as a pre-release, `vX.Y.Z` as the latest stable. Asset names are `{tool}-{target}.tar.xz` with no commit hash — the release body lines are the record of which commit each target was built from, and the scheduler's nightly staleness check parses them.

### Per-tool directories

There are no per-tool READMEs. Only tools with build customization have a directory:

- `gopls/` — `.goreleaser.yaml` (the only Go tool, so the only such file)
- `tree-sitter/` — `bindgen.patch`
- `mdcat/` — `vendored-curl.patch`
- `telemt/` — `macos-cfg-import.patch`

Each patch is applied by an `if: inputs.name == '<tool>'` step in `build-rust.yml`. All three fail loudly if the patch no longer applies; `tree-sitter` additionally skips gracefully when upstream lacks `crates/generate/Cargo.toml` (older releases).

## Common tasks

### Add a new tool

1. Add an entry to `build.json` with the right `type`, `upstream`, `bin`, `build_args`, target booleans, and `repo`. Keys are ordered alphabetically; inner keys follow `bin, type, build_args, target_*, upstream, repo` (`disabled` first when present).
2. Create the sub-repo: `gh repo create zydou/<tool>-binary --public --add-readme --description "Nightly cross-compiled builds of <tool>"`, then replace the default README with the standard template (copy any existing `zydou/*-binary` README and swap the tool name).
3. For Go tools, add a `<tool>/.goreleaser.yaml` (see `gopls/.goreleaser.yaml`).
4. For Rust tools needing a patch, add a `<tool>/` directory with the patch and a name-guarded step in `build-rust.yml`.
5. Push to `main` — the scheduler picks it up immediately and dispatches all stale targets.

### Trigger a manual build

Use **Actions → Build Rust / Build Go → Run workflow** on GitHub, supplying the tool's `build.json` values.

### Test changes locally

There is no local build harness.
The Python scripts (`scheduler.py`, `uploader.py`) require `GITHUB_TOKEN` and `GITHUB_REPOSITORY` env vars and talk to the GitHub API.
The actual compilation happens inside GitHub Actions runners.
Validate by pushing to `main` and watching the workflow runs.

## Conventions

- Asset naming must stay consistent: `{tool}-{target}.tar.xz` for rust, `{tool}-{os}-{arch}.tar.xz` for go (e.g. `gopls-linux-amd64.tar.xz`) — no commit hash in filenames. The scheduler, uploader, and the nightly staleness check (release body) all depend on these patterns. The Go form comes from `gopls/.goreleaser.yaml`'s `name_template`, which the workflow rewrites to use the tool name.
- `build.json` keys are ordered alphabetically (maintained by convention).
- **Binary name vs tool name**: the `bin` field can differ from the dict key. Current mismatches: `igrep`→`ig`, `repgrep`→`rgr`.
- New tools normally only need `build.json` + the sub-repo; edit workflow YAML only for special cases (patches).
- Rust release profile is hardened in `build-rust.yml`: `strip = true`, `opt-level = "z"`, `lto = true`, `codegen-units = 1`, `panic = "abort"`.
- `--locked` is omitted for `bore`, `mdcat`, and `tree-sitter` because their upstream `Cargo.lock` is frequently out of sync with `Cargo.toml` on HEAD.
- The active state lives in `build.json` + the workflow YAMLs, not in git history — early `feat:` commits that added per-tool READMEs, the tmux C build, and `hoard/openssl.patch` were deleted in `2d95f02` and their files no longer exist.

## Known quirks

- `TARGET_SHA_RE` is duplicated in `scheduler.py` and `uploader.py` and must be kept in sync. The trailing `.*$` is load-bearing: `uploader.py` rebuilds the body from `group(0)` of the sibling record lines, so a match ending at the SHA truncates the link's closing `)` off every untouched line.
- Nightly staleness is judged from the release **body**; tag staleness is judged from **asset presence** — tag commits are immutable, so an existing tag asset is assumed built from that tag.
- The scheduler always dispatches the highest-semver tag, even when the release already exists. The per-asset dedup inside `dispatch_rust`/`dispatch_go` is what prevents redundant runs.
- `build-go.yml` passes `GORELEASER_CURRENT_TAG` on tag releases because upstream tags like `gopls/v0.23.0-pre.2` contain a slash and are not valid semver, which breaks goreleaser's checksum file path.
- `dispatch_go` builds all 4 targets in one workflow run regardless of which are stale, so a single missing target costs a full rebuild.
- The `macos-26-intel` runner is listed in `build-rust.yml`'s `runner` choices but is never selected by `scheduler.py` — it is only for manual runs.
