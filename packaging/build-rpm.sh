#!/bin/sh
# Build dist/cinema-player-0.3.6-1.noarch.rpm from the repository root.
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
top="$root/build/rpm"
mkdir -p "$top/BUILD" "$top/RPMS" "$top/SOURCES" "$top/SPECS" "$top/SRPMS" "$root/dist"

rpmbuild -bb "$root/packaging/cinema-player.spec" \
    --define "_topdir $top" \
    --define "srcroot $root"

cp -f "$top/RPMS/noarch/cinema-player-0.3.6-1.noarch.rpm" "$root/dist/"
echo "Built $root/dist/cinema-player-0.3.6-1.noarch.rpm"
