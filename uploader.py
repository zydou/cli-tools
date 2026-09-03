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
        print(f"Creating release {name} [{self.repo}]")
        subprocess.run(  # noqa: S602
            [
                "gh", "release", "create", name,
                "--prerelease",
                "-n", name,
                "-t", name,
                "-R", self.repo,
            ],
            check=False,
        )

    def edit_release_body(self, name: str, ref: str, upstream: str) -> None:
        release = self.get_release(name)
        if release is None:
            return
        now = datetime.now(ZoneInfo("UTC"))
        body = (
            f"Build at {now:%Y-%m-%d %H:%M:%S} "
            f"based on [{ref[:7]}](https://github.com/{upstream}/tree/{ref})"
        )
        api = f"https://api.github.com/repos/{self.repo}/releases/{release['id']}"
        requests.patch(
            api, headers=HEADERS,
            json={"tag_name": name, "body": body, "prerelease": True},
            timeout=30,
        )

    def upload_asset(self, path: str | Path, release_name: str) -> None:
        path = Path(path).resolve()
        assert path.exists(), f"File not found: {path}"
        if self.get_release(release_name) is None:
            self.create_release(release_name)
        print(f"Uploading {path.name} to {release_name} [{self.repo}]")
        subprocess.run(  # noqa: S602
            [
                "gh", "release", "upload", release_name,
                "--clobber",
                "--", str(path),
            ],
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
