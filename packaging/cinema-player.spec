Name:           cinema-player
Version:        0.3.6
Release:        1
Summary:        Cinema video player for a projector booth
License:        Copyright (C) 2026 Thomas Winkler
URL:            http://cinema-player.github.io
BuildArch:      noarch
%global _binary_payload w9.xzdio

# Fedora/RHEL names, with the openSUSE name as an alternative.
Requires:       python3 >= 3.12
Requires:       (python3-tkinter or python3-tk)
Requires:       mpv
Requires:       (ffmpeg or ffmpeg-free)
Requires:       (xorg-x11-server-utils or xrandr)
Requires:       (xorg-x11-font-utils or mkfontscale)
Requires:       edid-decode
Recommends:     mutter
Recommends:     kscreen

%description
Cinema Player runs two mpv instances: one on the projector and one in the
booth window. The playlist holds films and stills. The projector picture
stays free of menus and on-screen text.

On X11 the projector mode is set with xrandr. GNOME on Wayland uses gdctl
(mutter). KDE on Wayland uses kscreen-doctor (kscreen). DMX over a USB
interface needs the user in the dialout group.

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor/64x64/apps
install -d %{buildroot}%{_datadir}/cinema-player/python
install -d %{buildroot}%{_datadir}/cinema-player/manual
install -m 0755 %{srcroot}/debian/cinema-player.wrapper %{buildroot}%{_bindir}/cinema-player
install -m 0644 %{srcroot}/debian/cinema-player.desktop %{buildroot}%{_datadir}/applications/cinema-player.desktop
install -m 0644 %{srcroot}/assets/logo/cinema-player-icon.png %{buildroot}%{_datadir}/icons/hicolor/64x64/apps/cinema-player.png
for src in %{srcroot}/python/*.py; do
    case $(basename "$src") in test_*) continue ;; esac
    install -m 0644 "$src" %{buildroot}%{_datadir}/cinema-player/python/
done
cp -a %{srcroot}/assets %{srcroot}/media %{buildroot}%{_datadir}/cinema-player/
cp -a %{srcroot}/manual/index.html %{srcroot}/manual/style.css %{srcroot}/manual/images %{buildroot}%{_datadir}/cinema-player/manual/
install -m 0644 %{srcroot}/pyproject.toml %{srcroot}/COPYRIGHT %{buildroot}%{_datadir}/cinema-player/
find %{buildroot} -type d -name __pycache__ -exec rm -rf {} +
find %{buildroot} -name '*.pyc' -delete

%post
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q %{_datadir}/applications || :
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q %{_datadir}/icons/hicolor || :
fi

%postun
if [ "$1" -eq 0 ]; then
    if [ -x /usr/bin/update-desktop-database ]; then
        update-desktop-database -q %{_datadir}/applications || :
    fi
    if [ -x /usr/bin/gtk-update-icon-cache ]; then
        gtk-update-icon-cache -q %{_datadir}/icons/hicolor || :
    fi
fi

%files
%{_bindir}/cinema-player
%{_datadir}/applications/cinema-player.desktop
%{_datadir}/icons/hicolor/64x64/apps/cinema-player.png
%{_datadir}/cinema-player

%changelog
* Mon Oct 26 2026 Thomas Winkler <thomas.winkler@iggmp.net> - 0.3.6-1
- Cleaning up of the user interface
- Many small bugfixes
