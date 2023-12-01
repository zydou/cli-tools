#!/bin/bash
set -e
set -x

ROOT="$(pwd)"
PATH="$HOME/.local/bin:$PATH"
GITDIR="$ROOT/upstream"
KEY_NAME="${NAME//-/_}"  # replace - with _
LDFLAGS=$(jq -r ".$KEY_NAME.ldflags" build.json)
BIN_NAME=$(jq -r ".$KEY_NAME.bin" build.json)

function install_dasel() {
    if [ ! -f "$HOME/.local/bin/dasel" ]; then
        mkdir -p "$HOME/.local/bin"
        curl -o "$HOME/.local/bin/dasel" -sSLf https://github.com/TomWright/dasel/releases/download/v2.5.0/dasel_linux_amd64
        chmod +x "$HOME/.local/bin/dasel"
    fi
}

function pre_build() {
    # pre-build step runs only once
    cd "$GITDIR"

    install_dasel

    # delete repo .goreleaser.yml
    if [ -f "$GITDIR/.goreleaser.yml" ]; then
        rm -f "$GITDIR/.goreleaser.yml"
    fi

    # setup .goreleaser.yaml
    cp -f "$ROOT/$NAME/.goreleaser.yaml" "$GITDIR/.goreleaser.yaml"
    dasel put -f "$GITDIR/.goreleaser.yaml" --value "$NAME" "project_name"
    dasel put -f "$GITDIR/.goreleaser.yaml" --value "$BIN_NAME" "builds.[0].binary"
    dasel put -f "$GITDIR/.goreleaser.yaml" --value "$LDFLAGS" "builds.[0].ldflags"
    cat "$GITDIR/.goreleaser.yaml"
}

function build() {
    cd "$GITDIR"
    goreleaser release --config "$GITDIR/.goreleaser.yaml" --auto-snapshot --clean
}

function post_build() {
    # post-build step runs only once
    cd "$GITDIR"
}

# main
pre_build
build
post_build