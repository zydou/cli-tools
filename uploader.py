#! /usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import subprocess
from pathlib import Path

import requests


class Github:
    def __init__(self, repo: str = os.getenv("GITHUB_REPOSITORY", "")) -> None:
        self.repo = repo
        assert self.repo, "Repo is not set"
        self.releases = {}
        self.assets = {}

    def get_releases(self) -> dict[str, dict]:
        print(f"Fetching releases for {self.repo}")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        all_releases = []
        per_page = 100  # maximum is 100
        page = 1
        res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=30).json()
        all_releases.extend(res)
        while len(res) == per_page:
            page += 1
            res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=30).json()
            all_releases.extend(res)
        print(f"Found {len(all_releases)} releases")
        self.releases = {release["name"]: release for release in all_releases}
        return self.releases

    def get_release_assets(self) -> dict[str, list]:
        print(f"Fetching release assets for {self.repo}")
        if not self.releases:
            self.releases = self.get_releases()
        self.assets = {name: [asset["name"] for asset in release["assets"]] for name, release in self.releases.items()}
        return self.assets

    def delete_release(self, release_name: str):
        print(f"Delete {release_name} [{self.repo}]")
        command = f"gh release delete '{release_name}' --cleanup-tag --yes"
        subprocess.run(command, shell=True, check=False)  # noqa: S602

    def upload_asset(self, path: str | Path, release_name: str, *, clean=False):
        path = Path(path).resolve()
        assert path.exists(), f"File not found: {path}"
        if not self.releases:
            self.releases = self.get_releases()
            self.assets = self.get_release_assets()
        if release_name not in self.releases:
            print(f"Creating release {release_name} [{self.repo}]")
            command = f"gh release create '{release_name}' --prerelease -n '{release_name}' -t '{release_name}' -R '{self.repo}' > /dev/null 2>&1 || true"
            subprocess.run(command, shell=True, check=False)  # noqa: S602
            self.assets[release_name] = []
        print(f"Uploading {path.name} to {release_name} [{self.repo}]")
        command = f"gh release upload --clobber '{release_name}' -- '{path.as_posix()}'"
        subprocess.run(command, shell=True, check=False)  # noqa: S602
        self.assets[release_name].append(path.name)
        if clean:
            path.unlink(missing_ok=True)


def main():
    file_path = Path(args.path)
    assets = gh.get_release_assets().get(args.name, [])
    if f"{args.name}-{args.target}-{args.ref[:7]}.tar.xz" in assets:
        print(f"Skipping {file_path.name} as it already exists")
        return
    gh.upload_asset(file_path, args.name, clean=False)
    new_path = file_path.with_name(f"{args.name}-{args.target}-{args.ref[:7]}.tar.xz")
    file_path.rename(new_path)
    gh.upload_asset(new_path, args.name, clean=True)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Description of the ArgumentParser")
    parser.add_argument("--name", type=str, required=True, help="tool name")
    parser.add_argument("--target", type=str, required=True, help="build target")
    parser.add_argument("--path", type=str, required=True, help="tarball path")
    parser.add_argument("--ref", type=str, required=True, help="remote ref")
    args = parser.parse_args()
    gh = Github()
    main()
