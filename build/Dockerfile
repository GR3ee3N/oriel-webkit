FROM debian:13.1-slim@sha256:a347fd7510ee31a84387619a492ad6c8eb0af2f2682b916ff3e643eb076f925a
ARG DEBIAN_SNAPSHOT
RUN rm -f /etc/apt/sources.list.d/* && \
    printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s/ trixie main\n' "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
        bc bison build-essential ca-certificates cpio curl file flex gawk \
        gettext git libncurses-dev locales patch perl pkg-config \
        python3 rsync shellcheck unzip wget xz-utils && \
    rm -rf /var/lib/apt/lists/* && \
    localedef -i en_US -f UTF-8 en_US.UTF-8
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
WORKDIR /work
