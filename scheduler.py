#! /usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path

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

    def get_release_assets(self) -> dict[str, list]:
        print(f"Fetching release assets for {self.repo}")
        if not self.releases:
            self.releases = self.get_releases()
        self.assets = {name: [asset["name"] for asset in release["assets"]] for name, release in self.releases.items()}
        return self.assets

    def get_head_commit(self, repo: str | None = None) -> str:
        if repo is None:
            repo = self.repo
        print(f"Fetching HEAD commit for {repo}")
        return requests.get(f"https://api.github.com/repos/{repo}/commits/HEAD", headers=HEADERS, timeout=30).json()["sha"]

    def trigger_workflow(self, workflow: str, inputs: dict) -> int:
        print(f"Triggering workflow for {inputs['name']}-{inputs['target']}")
        api = f"https://api.github.com/repos/{self.repo}/actions/workflows/{workflow}.yml/dispatches"
        data = {"ref": "main", "inputs": inputs}
        response = requests.post(api, headers=HEADERS, json=data, timeout=30)
        assert response.status_code == 204, f"Failed to trigger workflow: {response.text}"
        return response.status_code


def build_rust(name: str, info: dict, remote_ref: str):
    assets = gh.get_release_assets().get(name, [])
    workflow_inputs = {
        "name": name,
        "upstream": info["upstream"],
        "ref": remote_ref,
        "binary_name": info["bin"],
        "args": info["build_args"],
        "runner": "ubuntu-latest",
        "cross": True,
    }
    if info["target_x86_64_linux_musl"] and f"{name}-x86_64-unknown-linux-musl-{remote_ref[:7]}.tar.xz" not in assets:
        gh.trigger_workflow("build-rust", workflow_inputs | {"target": "x86_64-unknown-linux-musl"})

    if info["target_x86_64_linux_gnu"] and f"{name}-x86_64-unknown-linux-gnu-{remote_ref[:7]}.tar.xz" not in assets:
        gh.trigger_workflow("build-rust", workflow_inputs | {"target": "x86_64-unknown-linux-gnu"})

    if info["target_aarch64_linux_musl"] and f"{name}-aarch64-unknown-linux-musl-{remote_ref[:7]}.tar.xz" not in assets:
        gh.trigger_workflow("build-rust", workflow_inputs | {"target": "aarch64-unknown-linux-musl"})

    if info["target_aarch64_linux_gnu"] and f"{name}-aarch64-unknown-linux-gnu-{remote_ref[:7]}.tar.xz" not in assets:
        gh.trigger_workflow("build-rust", workflow_inputs | {"target": "aarch64-unknown-linux-gnu"})

    if info["target_x86_64_darwin"] and f"{name}-x86_64-apple-darwin-{remote_ref[:7]}.tar.xz" not in assets:
        gh.trigger_workflow(
            "build-rust",
            workflow_inputs
            | {
                "target": "x86_64-apple-darwin",
                "runner": "macos-13",
                "cross": False,
            },
        )

    if info["target_aarch64_darwin"] and f"{name}-aarch64-apple-darwin.tar.xz" not in assets:
        gh.trigger_workflow(
            "build-rust",
            workflow_inputs
            | {
                "target": "aarch64-apple-darwin",
                "runner": "macos-14",
                "cross": False,
            },
        )


def build_golang(name: str, info: dict, remote_ref: str):
    assets = gh.get_release_assets().get(name, [])
    workflow_inputs = {
        "name": name,
        "upstream": info["upstream"],
        "ref": remote_ref,
        "ldflags": info["ldflags"],
        "goversion": info["goversion"],
    }
    if f"{name}-linux-amd64.tar.xz" not in assets:
        gh.trigger_workflow("build-go", workflow_inputs)


def main():
    with Path("build.json").open() as f:
        build_info = json.load(f)
    for name, info in build_info.items():
        print(f"Processing {name}")
        remote_ref = gh.get_head_commit(info["upstream"])
        if info.get("type") == "rust":
            build_rust(name, info, remote_ref)
        if info.get("type") == "golang":
            build_golang(name, info, remote_ref)


if __name__ == "__main__":
    gh = Github()
    main()
