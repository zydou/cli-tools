#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Per-tool nightly + tag release dispatcher.

Runs on cron and on every push to main that touches build.json /
scheduler.py / scheduler.yml. For each enabled tool in build.json:

1. Fetch upstream HEAD commit.
2. For the per-tool sub-repo, ensure the `nightly` release has every
   target's tarball. If any are missing, dispatch a build for them
   with `ref=HEAD` and `release=nightly`.
3. Fetch upstream tags, normalize each one through the per-tool
   TAG_RULES table. For tags that pass the whitelist and whose
   release is not yet in the sub-repo, and whose commit differs
   from HEAD, dispatch a build with `ref=tag_sha` and
   `release=normalized_name`.
"""

import json
import os
import re
from pathlib import Path

import requests

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "X-GitHub-Api-Version": "2022-11-28",
}


class Github:
    """A GitHub API client scoped to a single repo."""

    def __init__(self, repo: str = os.getenv("GITHUB_REPOSITORY", "")) -> None:
        self.repo = repo
        assert self.repo, "Repo is not set"
        self._releases: dict[str, dict] | None = None
        self._tags: list[dict] | None = None

    def _paginate(self, path: str) -> list:
        results = []
        page = 1
        per_page = 100
        while True:
            res = requests.get(
                f"https://api.github.com/repos/{self.repo}/{path}?per_page={per_page}&page={page}",
                headers=HEADERS, timeout=30,
            )
            res.raise_for_status()
            chunk = res.json()
            results.extend(chunk)
            if len(chunk) < per_page:
                break
            page += 1
        return results

    def get_commit(self, ref: str = "HEAD") -> str:
        print(f"Fetching commit for {self.repo}@{ref}")
        res = requests.get(
            f"https://api.github.com/repos/{self.repo}/commits/{ref}",
            headers=HEADERS, timeout=30,
        )
        res.raise_for_status()
        return res.json()["sha"]

    def get_releases(self) -> dict[str, dict]:
        if self._releases is not None:
            return self._releases
        print(f"Fetching releases for {self.repo}")
        self._releases = {r["name"]: r for r in self._paginate("releases")}
        return self._releases

    def get_release_asset_names(self, release_name: str) -> set[str]:
        release = self.get_releases().get(release_name)
        if release is None:
            return set()
        return {a["name"] for a in release.get("assets", [])}

    def get_tags(self) -> list[dict]:
        if self._tags is not None:
            return self._tags
        print(f"Fetching tags for {self.repo}")
        self._tags = self._paginate("tags")
        return self._tags

    def get_tag_sha(self, tag_name: str) -> str:
        for tag in self.get_tags():
            if tag["name"] == tag_name:
                return tag["commit"]["sha"]
        raise KeyError(f"tag {tag_name!r} not found in {self.repo}")

    def trigger_workflow(self, workflow: str, inputs: dict) -> int:
        print(f"Triggering workflow for {inputs['name']}-{inputs.get('target')} ({inputs.get('release')})")
        api = f"https://api.github.com/repos/{self.repo}/actions/workflows/{workflow}.yml/dispatches"
        res = requests.post(
            api, headers=HEADERS,
            json={"ref": "main", "inputs": inputs}, timeout=30,
        )
        assert res.status_code == 204, f"Failed to trigger workflow: {res.text}"
        return res.status_code


# --- Target selection (shared by rust and go dispatchers) -----------

RUST_TARGETS = [
    # (target_triple, build_args_suffix, runner, cross)
    ("x86_64-unknown-linux-musl",     "x86_64-unknown-linux-musl",     "ubuntu-latest",    True),
    ("x86_64-unknown-linux-gnu",      "x86_64-unknown-linux-gnu",      "ubuntu-latest",    True),
    ("aarch64-unknown-linux-musl",    "aarch64-unknown-linux-musl",    "ubuntu-latest",    True),
    ("aarch64-unknown-linux-gnu",     "aarch64-unknown-linux-gnu",     "ubuntu-latest",    True),
    ("x86_64-apple-darwin",           "x86_64-apple-darwin",           "macos-15-intel",   False),
    ("aarch64-apple-darwin",          "aarch64-apple-darwin",          "macos-latest",     False),
]


def rust_targets(info: dict) -> list[tuple[str, str, str, bool]]:
    key_map = {
        "x86_64-unknown-linux-musl":   "target_x86_64_linux_musl",
        "x86_64-unknown-linux-gnu":    "target_x86_64_linux_gnu",
        "aarch64-unknown-linux-musl":  "target_aarch64_linux_musl",
        "aarch64-unknown-linux-gnu":   "target_aarch64_linux_gnu",
        "x86_64-apple-darwin":         "target_x86_64_darwin",
        "aarch64-apple-darwin":        "target_aarch64_darwin",
    }
    out = []
    for triple, label, runner, cross in RUST_TARGETS:
        if info.get(key_map[triple]):
            out.append((triple, label, runner, cross))
    return out


def go_targets(info: dict) -> list[str]:
    """gopls builds 4 targets via goreleaser — always returns the same list
    if the tool is a Go tool (the go-target_* booleans are not used)."""
    if info.get("type") != "golang":
        return []
    return ["linux-amd64", "linux-arm64", "darwin-amd64", "darwin-arm64"]


# --- Tag → release-name normalization ------------------------------

# Each rule has:
#   match:  compiled regex matched against the upstream tag name
#   release: callable(re.match) -> release name
# `default` is used when no per-tool rule applies.

TAG_RULES: dict[str, dict] = {
    "mdcat": {
        "match": re.compile(r"^(?:mdcat|mdless)-(\d+\.\d+\.\d+)$"),
        "release": lambda m: f"v{m.group(1)}",
    },
    "rust-analyzer": {
        "match": re.compile(r"^(\d{4}-\d{2}-\d{2})$"),
        "release": lambda m: m.group(1),
    },
    "taplo": {
        "match": re.compile(r"^(\d+\.\d+\.\d+)$"),  # bare semver only
        "release": lambda m: f"v{m.group(1)}",
    },
    "gopls": {
        "match": re.compile(r"^gopls/v(\d+\.\d+\.\d+)$"),
        "release": lambda m: f"v{m.group(1)}",
    },
    "_default": {
        "match": re.compile(r"^v?(\d+\.\d+\.\d+)$"),
        "release": lambda m: f"v{m.group(1)}",
    },
}


def normalize_tag(tool: str, tag_name: str) -> str | None:
    """Return the release name for a given upstream tag, or None to skip."""
    rule = TAG_RULES.get(tool) or TAG_RULES["_default"]
    m = rule["match"].match(tag_name)
    if m is None:
        return None
    return rule["release"](m)


# --- Per-tool dispatch ---------------------------------------------

def dispatch_rust(
    tool_gh: Github,
    main_gh: Github,
    name: str,
    info: dict,
    ref: str,
    release: str,
):
    for triple, target, runner, cross in rust_targets(info):
        # skip if this target's asset is already in the release
        asset = f"{name}-{target}.tar.xz"
        if asset in tool_gh.get_release_asset_names(release):
            continue
        print(f"  dispatch {name}/{release}/{target}")
        main_gh.trigger_workflow(
            "build-rust",
            {
                "name": name,
                "upstream": info["upstream"],
                "ref": ref,
                "binary_name": info["bin"],
                "args": info["build_args"],
                "target": triple,
                "runner": runner,
                "cross": "true" if cross else "false",
                "release": release,
                "repo": info["repo"],
            },
        )


def dispatch_go(
    tool_gh: Github,
    main_gh: Github,
    name: str,
    info: dict,
    ref: str,
    release: str,
):
    for target in go_targets(info):
        # gopls uses different asset naming: <name>-<os>-<arch>.tar.xz
        asset = f"{name}-{target}.tar.xz"
        if asset in tool_gh.get_release_asset_names(release):
            continue
        print(f"  dispatch {name}/{release}/{target}")
        main_gh.trigger_workflow(
            "build-go",
            {
                "name": name,
                "upstream": info["upstream"],
                "ref": ref,
                "goversion": info["goversion"],
                "ldflags": info["ldflags"],
                "target": target,
                "release": release,
                "repo": info["repo"],
            },
        )


# --- Main loop -----------------------------------------------------

def process_tool(name: str, info: dict):
    sub_repo = info["repo"]
    main_gh = Github()  # main repo (where this scheduler lives)
    upstream_gh = Github(repo=info["upstream"])
    tool_gh = Github(repo=sub_repo)

    head_sha = upstream_gh.get_commit("HEAD")

    # === nightly release ===
    print(f"[{name}] nightly")
    if info.get("type") == "rust":
        dispatch_rust(tool_gh, main_gh, name, info, head_sha, release="nightly")
    elif info.get("type") == "golang":
        dispatch_go(tool_gh, main_gh, name, info, head_sha, release="nightly")

    # === tag release (only the latest publishable tag) ===
    # Walk upstream tags in commit-date-desc order (the default from
    # GitHub's /tags endpoint). The first tag that survives
    # normalize_tag is the "latest" semantically meaningful release.
    # dispatch_rust/dispatch_go do per-asset dedup — they check each
    # target's asset in the tag release and only dispatch missing ones.
    # So we always dispatch the latest tag and let them decide; no need
    # for separate tag==HEAD or release-exists shortcuts.
    print(f"[{name}] tags")
    for tag in upstream_gh.get_tags():
        tag_name = tag["name"]
        release_name = normalize_tag(name, tag_name)
        if release_name is None:
            continue
        tag_sha = tag["commit"]["sha"]
        if info.get("type") == "rust":
            dispatch_rust(tool_gh, main_gh, name, info, tag_sha, release=release_name)
        elif info.get("type") == "golang":
            dispatch_go(tool_gh, main_gh, name, info, tag_sha, release=release_name)
        # only one tag release per cron run; the next one will catch up
        # next cycle
        break


def main():
    with Path("build.json").open() as f:
        build_info = json.load(f)
    for name, info in build_info.items():
        if str(info.get("disabled", "")).lower() in ["1", "true"]:
            continue
        if "repo" not in info:
            print(f"Skipping {name}: no 'repo' field in build.json")
            continue
        process_tool(name, info)


if __name__ == "__main__":
    main()
