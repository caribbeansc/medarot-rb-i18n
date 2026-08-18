#!/usr/bin/env bash
# Build hactool from source on a macOS runner and drop it in tools/bin/.
# SciresM ships only a Windows binary, so macOS builds it (small C + OpenSSL).
# Shared by the patcher workflow's macOS and Intel jobs.
set -euo pipefail

VER="${HACTOOL_VER:-1.4.0}"

brew install openssl@3
git clone --depth 1 --branch "$VER" https://github.com/SciresM/hactool.git hactool_src \
  || git clone --depth 1 https://github.com/SciresM/hactool.git hactool_src

cd hactool_src
cp config.mk.template config.mk
SSL="$(brew --prefix openssl@3)"
{
  echo "CFLAGS += -I$SSL/include"
  echo "LDFLAGS += -L$SSL/lib"
} >> config.mk
make -j3
cd ..

mkdir -p tools/bin
cp hactool_src/hactool tools/bin/hactool
chmod +x tools/bin/hactool
./tools/bin/hactool --help >/dev/null 2>&1 || true
