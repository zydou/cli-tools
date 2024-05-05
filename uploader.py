#! /usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import subprocess
from datetime import datetime, timedelta
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
        self.releases = {}
        self.assets = {}

    def get_releases(self) -> dict[str, dict]:
        print(f"Fetching releases for {self.repo}")
        if self.releases:
            return self.releases
        all_releases = []
        per_page = 100  # maximum is 100
        page = 1
        res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=HEADERS, timeout=30).json()
        all_releases.extend(res)
        while len(res) == per_page:
            page += 1
            res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=HEADERS, timeout=30).json()
            all_releases.extend(res)
        print(f"Found {len(all_releases)} releases")
        self.releases = {release["name"]: release for release in all_releases}
        return self.releases

    def get_release_assets(self) -> dict[str, dict]:
        print(f"Fetching release assets for {self.repo}")
        if self.assets:
            return self.assets
        if not self.releases:
            self.releases = self.get_releases()
        self.assets = {
            name: {
                asset["name"]: {
                    "updated_at": asset["updated_at"],
                    "id": asset["id"],
                }
                for asset in release["assets"]
            }
            for name, release in self.releases.items()
        }
        return self.assets

    def delete_release(self, release_name: str):
        print(f"Delete {release_name} [{self.repo}]")
        command = f"gh release delete '{release_name}' --cleanup-tag --yes"
        subprocess.run(command, shell=True, check=False)  # noqa: S602

    def delete_asset(self, asset_id: int):
        print(f"Delete asset {asset_id} [{self.repo}]")
        requests.delete(f"https://api.github.com/repos/{self.repo}/releases/assets/{asset_id}", headers=HEADERS, timeout=30)

    def edit_release(self, release_name: str):
        print(f"Edit release {release_name} [{self.repo}]")
        release = self.get_releases().get(release_name, {})
        api = f"https://api.github.com/repos/{self.repo}/releases/{release['id']}"
        now = datetime.now(ZoneInfo("UTC"))
        body = f"Build at {now:%Y-%m-%d %H:%M:%S} based on [{args.ref[:7]}](https://github.com/{args.upstream}/tree/{args.ref})"
        data = {"tag_name": release_name, "body": body, "prerelease": True}
        requests.patch(api, headers=HEADERS, json=data, timeout=30)

    def upload_asset(self, path: str | Path, release_name: str, *, clean=False):
        path = Path(path).resolve()
        assert path.exists(), f"File not found: {path}"
        if not self.releases:
            self.releases = self.get_releases()
        if release_name not in self.releases:
            print(f"Creating release {release_name} [{self.repo}]")
            command = f"gh release create '{release_name}' --prerelease -n '{release_name}' -t '{release_name}' -R '{self.repo}' > /dev/null 2>&1 || true"
            subprocess.run(command, shell=True, check=False)  # noqa: S602
        print(f"Uploading {path.name} to {release_name} [{self.repo}]")
        command = f"gh release upload --clobber '{release_name}' -- '{path.as_posix()}'"
        subprocess.run(command, shell=True, check=False)  # noqa: S602
        if clean:
            path.unlink(missing_ok=True)


def delete_old_assets(assets: dict):
    """Delete old assets.

    Assets matching ALL of the following criteria will be deleted:

    1. older than 3 months
    2. not the last 2 assets

    Args:
        assets (dict): assets to filter
    """
    assets = dict(sorted(assets.items(), key=lambda x: x[1]["updated_at"], reverse=False))
    assets_without_nightly = {k: v for k, v in assets.items() if len(k.split("-")[-1]) == 14}  # end with "ref[:7].tar.xz"
    commits = []
    for name in assets_without_nightly:
        if name.removesuffix(".tar.xz").split("-")[-1] not in commits:
            commits.append(name.removesuffix(".tar.xz").split("-")[-1])
    last_2_commits = commits[-2:]
    for asset_name, info in assets_without_nightly.items():
        commit = asset_name.removesuffix(".tar.xz").split("-")[-1]
        if commit in last_2_commits:
            continue
        updated_time = datetime.strptime(info["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
        three_months_ago = datetime.now(ZoneInfo("UTC")) - timedelta(days=90)
        if updated_time < three_months_ago:
            print(f"Deleting {asset_name}")
            gh.delete_asset(info["id"])


def main():
    file_path = Path(args.path)
    assets = gh.get_release_assets().get(args.name, {})
    if f"{args.name}-{args.target}-{args.ref[:7]}.tar.xz" in assets:
        print(f"Skipping {file_path.name} as it already exists")
        return
    delete_old_assets(assets)
    gh.upload_asset(file_path, args.name, clean=False)
    new_path = file_path.with_name(f"{args.name}-{args.target}-{args.ref[:7]}.tar.xz")
    file_path.rename(new_path)
    gh.upload_asset(new_path, args.name, clean=True)
    gh.edit_release(args.name)
    gh.edit_release(args.name)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Description of the ArgumentParser")
    parser.add_argument("--name", type=str, required=True, help="tool name")
    parser.add_argument("--target", type=str, required=True, help="build target")
    parser.add_argument("--path", type=str, required=True, help="tarball path")
    parser.add_argument("--ref", type=str, required=True, help="remote ref")
    parser.add_argument("--upstream", type=str, required=True, help="upstream repo")
    args = parser.parse_args()
    gh = Github()
    main()
