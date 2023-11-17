#!/bin/bash

ROOT="$(pwd)"
PATH="$HOME/.cargo/bin:$PATH"
CROSS_VERSION="v0.2.5"

BUILD_ARGS=$(jq -r ".$NAME.build_args" build.json)
BIN_NAME=$(jq -r ".$NAME.bin" build.json)

if [ ! -d ".build_$NAME" ]; then
mkdir ".build_$NAME"
curl -sSLf -o "$NAME-src.tar.gz" "$DOWNLOAD_URL"
tar -C ".build_$NAME" --strip-components=1 -xzf "$NAME-src.tar.gz"
rm -f "$NAME-src.tar.gz"
fi
cd ".build_$NAME" || exit

# Install cross
if [[ ! -x "$HOME/.cargo/bin/cross" && "$(uname -s)" = "Linux" ]]; then
    curl -sSLfO "https://github.com/cross-rs/cross/releases/download/$CROSS_VERSION/cross-x86_64-unknown-linux-musl.tar.gz"
    tar -C "$HOME/.cargo/bin" -xzf cross-x86_64-unknown-linux-musl.tar.gz
    rm -f cross-x86_64-unknown-linux-musl.tar.gz
fi

mkdir -p "$HOME/.cargo"
cat > "$HOME/.cargo/config.toml" <<EOF
[profile.release]
strip = true
EOF

function release() {
    local TARGET=$1
    mv "target/$TARGET/release/$BIN_NAME" "$BIN_NAME"
    tar -cJf "$NAME-$TARGET.tar.xz" "$BIN_NAME"

    gh release create "$NAME-${REMOTE_REF:0:7}" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME-${REMOTE_REF:0:7}" --repo "$REPO" || true
    gh release edit "$NAME-${REMOTE_REF:0:7}" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME-${REMOTE_REF:0:7}" --repo "$REPO" || true
    gh release delete-asset "$NAME-${REMOTE_REF:0:7}" "$NAME-$TARGET.tar.xz" --yes --repo "$REPO" || true
    gh release upload "$NAME-${REMOTE_REF:0:7}" "$NAME-$TARGET.tar.xz" --repo "$REPO"

    gh release create "$NAME" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME" --repo "$REPO" || true
    gh release edit "$NAME" --prerelease --notes "Nightly build $NAME based on https://github.com/$UPSTREAM/tree/$REMOTE_REF" --title "$NAME" --repo "$REPO" || true
    gh release delete-asset "$NAME" "$NAME-$TARGET.tar.xz" --yes --repo "$REPO" || true
    gh release upload "$NAME" "$NAME-$TARGET.tar.xz" --repo "$REPO"
}

# Pre-build steps
if [ "$NAME" = "hoard" ]; then
    git apply "$ROOT/hoard/openssl.patch"
fi

# Build & Release
if [ "$(uname -s)" = "Linux" ]; then
    eval "cross build ${BUILD_ARGS} --target x86_64-unknown-linux-gnu"
    release x86_64-unknown-linux-gnu

    eval "cross build ${BUILD_ARGS} --target x86_64-unknown-linux-musl"
    release x86_64-unknown-linux-musl

    eval "cross build ${BUILD_ARGS} --target aarch64-unknown-linux-gnu"
    release aarch64-unknown-linux-gnu

    eval "cross build ${BUILD_ARGS} --target aarch64-unknown-linux-musl"
    release aarch64-unknown-linux-musl

else
    eval "cargo build ${BUILD_ARGS} --target x86_64-apple-darwin"
    release aarch64-apple-darwin

    rustup target add aarch64-apple-darwin
    eval "cargo build ${BUILD_ARGS} --target aarch64-apple-darwin"
    release x86_64-apple-darwin
fi
