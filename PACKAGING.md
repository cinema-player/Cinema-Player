# New Debian and RPM package

Cinema Player ships one architecture-independent package for both formats. The `.deb` and the `.rpm` install the same tree under `/usr`: the launcher, the desktop entry, the icon, and the program files. They do not use Pixi. Build both from a checkout of the version you want to ship.

The package version follows `pyproject.toml`. A final `0.3.6` is spelled differently in each format:

| Place | Final `0.3.6` | Beta of that version |
| --- | --- | --- |
| `pyproject.toml` | `0.3.6` | `0.3.6` |
| Debian changelog and `debian/rules` | `0.3.6-1` | `0.3.6~beta-1` |
| Debian file | `dist/cinema-player_0.3.6-1_all.deb` | `dist/cinema-player_0.3.6~beta-1_all.deb` |
| RPM `Version` / `Release` | `0.3.6` / `1` | `0.3.6` / `beta1` |
| RPM file | `dist/cinema-player-0.3.6-1.noarch.rpm` | `dist/cinema-player-0.3.6-beta1.noarch.rpm` |

The Debian string `0.3.6~beta-1` is upstream `0.3.6~beta` plus Debian revision `1`. The tilde sorts before the final release, so apt upgrades `0.3.6~beta-1` to `0.3.6-1`. RPM keeps the dotted number in `Version` and the prerelease token in `Release`, with no hyphen inside `Release`.

Bump the Debian revision (`-2`, then `-3`) when the package scripts change and the program version does not. Leave `Version=` in `debian/cinema-player.desktop` as `1.0`; that is the desktop-entry spec, not the package version.

## 1. Set the version

Edit these four places so they name the same release.

`pyproject.toml`:

```toml
version = "0.3.6"
```

`debian/changelog`, new stanza at the top. The date must be the output of `date -R`:

```text
cinema-player (0.3.6-1) unstable; urgency=medium

  * What changed in this package.

 -- Thomas Winkler <thomas.winkler@iggmp.net>  Thu, 29 Oct 2026 12:33:00 +0100
```

`debian/rules`, the filename version, identical to the changelog parenthesis:

```make
version := 0.3.6-1
```

`packaging/cinema-player.spec`:

```spec
Version:        0.3.6
Release:        1
```

and a new `%changelog` entry:

```spec
* Thu Oct 29 2026 Thomas Winkler <thomas.winkler@iggmp.net> - 0.3.6-1
- What changed in this package.
```

`packaging/build-rpm.sh` copies one fixed filename. Point the comment, the `cp`, and the `echo` at `cinema-player-0.3.6-1.noarch.rpm` (or `cinema-player-0.3.6-beta1.noarch.rpm` for a beta). `dpkg-gencontrol` rewrites `debian/files`; do not edit that file.

## 2. Debian package

Install the build tool, then build from the repository root:

```bash
sudo apt install dpkg-dev
debian/rules binary
```

The result is `dist/cinema-player_<version>_all.deb`. Check the control version and the installed paths:

```bash
dpkg-deb -I dist/cinema-player_0.3.6-1_all.deb
dpkg-deb -c dist/cinema-player_0.3.6-1_all.deb
```

Install on Debian or Ubuntu:

```bash
sudo apt install ./dist/cinema-player_0.3.6-1_all.deb
```

## 3. RPM package

Install `rpm-build`, then build from anywhere:

```bash
sudo apt install rpm-build
packaging/build-rpm.sh
```

On openSUSE the package name is the same (`sudo zypper install rpm-build`). On Debian or Ubuntu use `sudo apt install rpm`. The result is `dist/cinema-player-<version>-<release>.noarch.rpm`.

```bash
rpm -qip dist/cinema-player-0.3.6-1.noarch.rpm
rpm -qlp dist/cinema-player-0.3.6-1.noarch.rpm
```

Install on Fedora or RHEL with `sudo dnf install ./dist/cinema-player-0.3.6-1.noarch.rpm`. On openSUSE use `sudo zypper install ./dist/cinema-player-0.3.6-1.noarch.rpm`.

## What goes into the package

Both recipes copy the working tree, skip `python/test_*.py`, and drop `__pycache__`. The payload is `python/*.py` (except tests), `assets/`, `media/`, `manual/index.html`, `manual/style.css`, `manual/images/`, `pyproject.toml`, and `COPYRIGHT`, plus `debian/cinema-player.wrapper` and `debian/cinema-player.desktop`. Dependencies stay in `debian/control` and the `Requires` lines of `packaging/cinema-player.spec`. The Debian maintainer scripts are `debian/postinst` and `debian/postrm`; the RPM equivalents are `%post` and `%postun` in the spec.
