#!/usr/bin/env bash
# Build hactool from source on a macOS runner and drop it in tools/bin/.
# SciresM ships only a Windows binary, so macOS builds it (small C + OpenSSL).
# Shared by the patcher workflow's macOS jobs.
#
# Usage:
#   build-hactool.sh            native build (arm64 on an Apple Silicon runner)
#   build-hactool.sh x86_64     cross-build an Intel binary on the ARM runner,
#                               using an x86_64 OpenSSL bottle from Homebrew
set -euo pipefail

VER="${HACTOOL_VER:-1.4.0}"
ARCH="${1:-}"

git clone --depth 1 --branch "$VER" https://github.com/SciresM/hactool.git hactool_src \
  || git clone --depth 1 https://github.com/SciresM/hactool.git hactool_src

if [ "$ARCH" = "x86_64" ]; then
  # The runner is Apple Silicon; fetch an Intel OpenSSL bottle and link against
  # it. clang cross-compiles to x86_64 with -arch, no Rosetta needed for the C.
  brew fetch --force --bottle-tag=ventura openssl@3
  BOTTLE="$(brew --cache --bottle-tag=ventura openssl@3)"
  mkdir -p ossl && tar xzf "$BOTTLE" -C ossl
  SSL="$(echo "$PWD"/ossl/openssl@3/*/)"
  ARCHFLAGS="-arch x86_64"
else
  brew install openssl@3
  SSL="$(brew --prefix openssl@3)"
  ARCHFLAGS=""
fi

cd hactool_src
cp config.mk.template config.mk
{
  echo "CFLAGS += $ARCHFLAGS -I${SSL}/include"
  echo "LDFLAGS += $ARCHFLAGS -L${SSL}/lib"
} >> config.mk
make -j3
cd ..

mkdir -p tools/bin
cp hactool_src/hactool tools/bin/hactool
chmod +x tools/bin/hactool
file tools/bin/hactool   # log the architecture so cross-builds are verifiable
