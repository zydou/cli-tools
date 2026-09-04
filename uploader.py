#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Upload a built tarball to a per-tool GitHub release.

Designed to work for both nightly and tag releases, and for both
rust and go tools. Asset names are
``{name}-{target}.tar.xz`` (no commit hash) — releases are
distinguished by their release name, not by per-asset filenames.

Behavior:
- Find or create the release named ``--release`` in the target repo.
- Upload the asset with ``gh release upload --clobber``. Same-named
  assets are replaced in place; other-target assets are preserved
  unchanged. We never delete assets — a temporarily-failing target
  keeps its previous-good tarball, so the release is never in a
  "missing target X" state.
- Edit the release body to record the build timestamp and upstream
  commit link. The body is updated on every successful upload.
"""

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# The build workflow injects GITHUB_TOKEN=<PAT> into the env, so we
# transparently use it for both REST calls and `gh` subprocesses
# (the latter via GH_TOKEN). GITHUB_TOKEN alone, on the cross-repo
# upload target, would 403.
HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "X-GitHub-Api-Version": "2022-11-28",
}


class Github:
    def __init__(self, repo: str = os.getenv("GITHUB_REPOSITORY", "")) -> None:
        self.repo = repo
        assert self.repo, "Repo is not set"

    def get_release(self, name: str) -> dict | None:
        api = f"https://api.github.com/repos/{self.repo}/releases/tags/{name}"
        res = requests.get(api, headers=HEADERS, timeout=30)
        if res.status_code == 200:
            return res.json()
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return None  # unreachable, for type checkers

    def create_release(self, name: str) -> None:
        # Use the REST API instead of `gh release create` because gh
        # will happily create duplicate releases with the same name
        # ("By default, the release is created even if there are no
        # new commits since the last release. This may result in the
        # same or duplicate release" — `gh release create --help`).
        # The REST endpoint returns 422 when the tag_name is taken.
        #
        # nightly releases are pre-releases; named tag releases
        # (e.g. v2.15.0) are marked as the latest stable release.
        prerelease = name == "nightly"
        print(f"Creating release {name} [{self.repo}] (prerelease={prerelease})")
        api = f"https://api.github.com/repos/{self.repo}/releases"
        payload = {
            "tag_name": name,
            "name": name,
            "body": name,
            "prerelease": prerelease,
        }
        res = requests.post(api, headers=HEADERS, json=payload, timeout=30)
        if res.status_code == 201:
            return
        if res.status_code == 422:
            # Tag already exists; another concurrent uploader raced us
            # to it. That's fine — the existing release is what we
            # want to upload to.
            return
        print(f"  create release returned {res.status_code}: {res.text}")

    def edit_release_body(self, name: str, ref: str, upstream: str) -> None:
        release = self.get_release(name)
        if release is None:
            return
        now = datetime.now(ZoneInfo("UTC"))
        body = (
            f"Build at {now:%Y-%m-%d %H:%M:%S} "
            f"based on [{ref[:7]}](https://github.com/{upstream}/tree/{ref})"
        )
        # Preserve the existing prerelease flag — nightly stays a
        # pre-release, tag releases stay as the latest stable.
        api = f"https://api.github.com/repos/{self.repo}/releases/{release['id']}"
        requests.patch(
            api, headers=HEADERS,
            json={"tag_name": name, "body": body, "prerelease": release["prerelease"]},
            timeout=30,
        )

    def upload_asset(self, path: str | Path, release_name: str) -> None:
        path = Path(path).resolve()
        assert path.exists(), f"File not found: {path}"
        if self.get_release(release_name) is None:
            self.create_release(release_name)
        print(f"Uploading {path.name} to {release_name} [{self.repo}]")
        # --repo is required because the workflow checks out the main repo
        # (zydou/cli-tools), so gh would infer the wrong target repo without
        # it. The REST-based get_release/create_release above already use
        # self.repo, so the upload must match.
        subprocess.run(  # noqa: S602
            [
                "gh", "release", "upload", release_name,
                "--repo", self.repo,
                "--clobber",
                "--", str(path),
            ],
            env={**os.environ, "GH_TOKEN": os.environ["GITHUB_TOKEN"]},
            check=False,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="tool name (release name prefix)")
    parser.add_argument("--target", required=True, help="build target")
    parser.add_argument("--path", required=True, help="tarball path to upload")
    parser.add_argument("--ref", required=True, help="upstream ref (commit SHA)")
    parser.add_argument("--upstream", required=True, help="upstream org/repo")
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY", ""),
        help="target repo (defaults to $GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--release",
        default="nightly",
        help="release name to upload to (default: nightly)",
    )
    args = parser.parse_args()

    # rename the on-disk tarball to the canonical name (no commit hash)
    file_path = Path(args.path)
    canonical = file_path.with_name(f"{args.name}-{args.target}.tar.xz")
    if file_path != canonical:
        file_path.rename(canonical)

    gh = Github(repo=args.repo)
    gh.upload_asset(canonical, args.release)
    gh.edit_release_body(args.release, args.ref, args.upstream)


if __name__ == "__main__":
    main()
