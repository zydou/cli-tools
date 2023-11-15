FROM buildpack-deps:xenial AS build

ENV CC=cc
ENV REALCC=cc
ENV CPPFLAGS="-P"
ENV HOME=/app
WORKDIR /app

# musl
ARG MUSL_VERSION
RUN mkdir -p "${HOME}/musl" && \
    cd "${HOME}/musl" && \
    curl -sSLfk -o "musl-${MUSL_VERSION}.tar.gz" "https://github.com/bminor/musl/archive/refs/tags/${MUSL_VERSION}.tar.gz" && \
    tar --strip-components 1 -xzf "musl-${MUSL_VERSION}.tar.gz" && \
    ./configure --enable-gcc-wrapper --disable-shared --prefix="${HOME}" --bindir="${HOME}/bin" --includedir="${HOME}/include" --libdir="${HOME}/lib" && \
    make && \
    make install && \
    cd "${HOME}" && \
    rm -rf "${HOME}/musl"

# libevent
ARG LIBEVENT_VERSION
ENV CC="/app/bin/musl-gcc -static"
RUN mkdir -p "${HOME}/libevent" && \
    cd "${HOME}/libevent" && \
    curl -sSLfk -o "libevent-${LIBEVENT_VERSION}.tar.gz" "https://github.com/libevent/libevent/releases/download/release-${LIBEVENT_VERSION}/libevent-${LIBEVENT_VERSION}.tar.gz" && \
    tar --strip-components 1 -xzf "libevent-${LIBEVENT_VERSION}.tar.gz" && \
    ./autogen.sh && \
    ./configure --prefix="${HOME}" --includedir="${HOME}/include" --libdir="${HOME}/lib" --disable-shared --disable-openssl --disable-libevent-regress --disable-samples && \
    make && \
    make install && \
    cd "${HOME}" && \
    rm -rf "${HOME}/libevent"

# ncurses
ARG NCURSES_VERSION
RUN mkdir -p "${HOME}/ncurses" && \
    cd "${HOME}/ncurses"  && \
    curl -sSLfk -o ncurses.tar.gz "https://github.com/mirror/ncurses/archive/refs/tags/${NCURSES_VERSION}.tar.gz"  && \
    tar --strip-components 1 -xzf ncurses.tar.gz  && \
    ./configure --prefix="${HOME}" --includedir="${HOME}/include" --libdir="${HOME}/lib" --enable-pc-files --with-pkg-config="${HOME}/lib/pkgconfig" --with-pkg-config-libdir="${HOME}/lib/pkgconfig" --without-ada --without-tests --without-manpages --with-ticlib --with-termlib --with-default-terminfo-dir=/usr/share/terminfo --with-terminfo-dirs=/etc/terminfo:/lib/terminfo:/usr/share/terminfo  && \
    make  && \
    make install  && \
    cd "${HOME}"  && \
    rm -rf "${HOME}/ncurses"

# tmux
ARG TMUX_VERSION
RUN apt-get update && \
    apt-get install -y --no-install-recommends bison  && \
    mkdir -p "${HOME}/tmux" && \
    cd "${HOME}/tmux" && \
    curl -sSLfk -o "tmux-${TMUX_VERSION}.tar.gz" "https://github.com/tmux/tmux/releases/download/${TMUX_VERSION}/tmux-${TMUX_VERSION}.tar.gz" && \
    tar --strip-components 1 -xzf "tmux-${TMUX_VERSION}.tar.gz" && \
    ./configure --prefix="${HOME}" --enable-static --includedir="${HOME}/include" --libdir="${HOME}/lib" CFLAGS="-I${HOME}/include" LDFLAGS="-L${HOME}/lib" CPPFLAGS="-I${HOME}/include" LIBEVENT_LIBS="-L${HOME}/lib -levent" LIBNCURSES_CFLAGS="-I${HOME}/include/ncurses" LIBNCURSES_LIBS="-L${HOME}/lib -lncurses" LIBTINFO_CFLAGS="-I${HOME}/include/ncurses" LIBTINFO_LIBS="-L${HOME}/lib -ltinfo" && \
    make && \
    make install && \
    strip "${HOME}/bin/tmux" && \
    cd "${HOME}" && \
    rm -rf "${HOME}/tmux"

# upx
ARG UPX_VERSION
RUN cp "${HOME}/bin/tmux" "${HOME}/bin/tmux-upx" && \
    curl -sSLfk -o "upx-${UPX_VERSION}.tar.xz" "https://github.com/upx/upx/releases/download/${UPX_VERSION}/upx-${UPX_VERSION#v}-amd64_linux.tar.xz" && \
    tar --strip-components 1 -xJf "upx-${UPX_VERSION}.tar.xz" && \
    ./upx --best --ultra-brute "${HOME}/bin/tmux-upx"

FROM scratch
COPY --from=build /app/bin/tmux /tmux
COPY --from=build /app/bin/tmux-upx /tmux-upx
