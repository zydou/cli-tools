#!/bin/bash
set -e
set -x

ROOT="$(pwd)"
GITDIR="$ROOT/src_$NAME"

function init_var() {
    PATH="$HOME/.cargo/bin:$PATH"
    CROSS_VERSION="v0.2.5"
    KEY_NAME="${NAME//-/_}"  # replace - with _
    BUILD_ARGS=$(jq -r ".$KEY_NAME.build_args" build.json)
    BIN_NAME=$(jq -r ".$KEY_NAME.bin" build.json)
    UPSTREAM=$(jq -r ".$KEY_NAME.upstream" build.json)
    TARGET_X86_64_LINUX_GNU=$(jq -r ".$KEY_NAME.target_x86_64_linux_gnu" build.json)
    TARGET_X86_64_LINUX_MUSL=$(jq -r ".$KEY_NAME.target_x86_64_linux_musl" build.json)
    TARGET_AARCH64_LINUX_GNU=$(jq -r ".$KEY_NAME.target_aarch64_linux_gnu" build.json)
    TARGET_AARCH64_LINUX_MUSL=$(jq -r ".$KEY_NAME.target_aarch64_linux_musl" build.json)
    TARGET_X86_64_DARWIN=$(jq -r ".$KEY_NAME.target_x86_64_darwin" build.json)
    TARGET_AARCH64_DARWIN=$(jq -r ".$KEY_NAME.target_aarch64_darwin" build.json)

    if [ "$(uname -s)" = "Linux" ]; then
        CARGO="cross"
        USE_CROSS="true"
    else
        CARGO="cargo"
        USE_CROSS="false"
    fi
}

function install_cross() {
    if [[ ! -x "$HOME/.cargo/bin/cross" && "$USE_CROSS" = "true" ]]; then
        curl -sSLfO "https://github.com/cross-rs/cross/releases/download/$CROSS_VERSION/cross-x86_64-unknown-linux-musl.tar.gz"
        tar -C "$HOME/.cargo/bin" -xzf cross-x86_64-unknown-linux-musl.tar.gz
        rm -f cross-x86_64-unknown-linux-musl.tar.gz
    fi
}

function create_cargo_config() {
mkdir -p "$HOME/.cargo"
cat > "$HOME/.cargo/config.toml" <<EOF
[profile.release]
strip = true
opt-level = "z"
lto = true
codegen-units = 1
panic = "abort"
EOF
}

function clone_repo() {
    if [ ! -d "$GITDIR" ]; then
    git clone --depth 1 "https://github.com/$UPSTREAM.git" "$GITDIR"
    fi
}

function release_target() {
    local TARGET=$1
    cd "$GITDIR/target/$TARGET/release"
    tar -cJf "$NAME-$TARGET.tar.xz" "$BIN_NAME"

    gh release create "$NAME-${REMOTE_REF:0:7}" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME-${REMOTE_REF:0:7}" --repo "$REPO" || true
    gh release edit "$NAME-${REMOTE_REF:0:7}" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME-${REMOTE_REF:0:7}" --repo "$REPO" || true
    gh release upload "$NAME-${REMOTE_REF:0:7}" "$NAME-$TARGET.tar.xz" --clobber --repo "$REPO"

    gh release create "$NAME" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME" --repo "$REPO" || true
    gh release edit "$NAME" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME" --repo "$REPO" || true
    gh release upload "$NAME" "$NAME-$TARGET.tar.xz" --clobber --repo "$REPO"
}

function pre_build_global() {
    # pre-build step runs only once
    cd "$GITDIR"

    # tweaks for individual tools
    if [[ "$NAME" = "hoard" && -f "$ROOT/hoard/openssl.patch" ]]; then
        git apply "$ROOT/hoard/openssl.patch"
    fi
}

function pre_build_steps() {
    # pre-build step runs for each target
    local TARGET=$1
    cd "$GITDIR"

    # install target toolchain if not use cross
    if [ "$USE_CROSS" = "false" ]; then
        rustup target add "$TARGET"
    fi

    if [[ "$NAME" = "bore" && -f "Cargo.lock" ]]; then
        rm -f Cargo.lock
    fi

    if [[ "$NAME" = "ripgrep" && -f "Cross.toml" ]]; then
        rm -f Cross.toml
    fi

    if [[ "$NAME" = "tealdeer" && -f "Cargo.lock" ]]; then
        rm -f Cargo.lock
    fi
}

function post_build_global() {
    # post-build step runs only once
    cd "$GITDIR"
}

function post_build_steps() {
    # post-build step runs for each target
    local TARGET=$1
    cd "$GITDIR"
    if [ -d "$GITDIR/target" ]; then
        rm -rf "$GITDIR/target"
    fi
}

function build_target() {
    local TARGET=$1
    cd "$GITDIR"
    pre_build_steps "$TARGET"
    eval "$CARGO build ${BUILD_ARGS} --target $TARGET"
    release_target "$TARGET"
    post_build_steps "$TARGET"
}

# main
init_var
install_cross
create_cargo_config
clone_repo
pre_build_global

if [ "$(uname -s)" = "Linux" ]; then
    if [ "$TARGET_X86_64_LINUX_GNU" = "true" ]; then
        build_target x86_64-unknown-linux-gnu
    fi

    if [ "$TARGET_X86_64_LINUX_MUSL" = "true" ]; then
        build_target x86_64-unknown-linux-musl
    fi

    if [ "$TARGET_AARCH64_LINUX_GNU" = "true" ]; then
        build_target aarch64-unknown-linux-gnu
    fi

    if [ "$TARGET_AARCH64_LINUX_MUSL" = "true" ]; then
        build_target aarch64-unknown-linux-musl
    fi
else
    if [ "$TARGET_X86_64_DARWIN" = "true" ]; then
        build_target x86_64-apple-darwin
    fi

    if [ "$TARGET_AARCH64_DARWIN" = "true" ]; then
        build_target aarch64-apple-darwin
    fi
fi

post_build_global
