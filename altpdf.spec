# RPM spec file for Редактор PDF Альт (AltPDF)
# Builds from a PyInstaller one-file binary.
#
# Build steps:
#   1. Install build deps:
#        apt-get install rpm-build python3-module-pyinstaller
#   2. Create the tarball from your source tree:
#        tar -czf ~/rpmbuild/SOURCES/altpdf-0.831.tar.gz \
#            --transform 's|^|altpdf-0.831/|' \
#            *.py icons/ resources.py help.pdf ghostscript/ AltPDF.spec
#   3. Place this file in ~/rpmbuild/SPECS/altpdf.spec
#   4. Build:
#        rpmbuild -bb ~/rpmbuild/SPECS/altpdf.spec

Name:           altpdf
Version:        0.831
Release:        alt1
Summary:        Редактор PDF файлов для Альт Рабочая станция
License:        Proprietary
Group:          Office
URL:            https://sng.ru

# Source tarball containing the Python source tree
Source0:        %{name}-%{version}.tar.gz

# ── Runtime deps that must be present on the target machine ──────────────────
# PyInstaller bundles Python + most libs, but the Qt platform plugin needs
# certain system libraries.  List the ones not bundled:
Requires:       libgcc1
Requires:       glibc

# ── Build deps ───────────────────────────────────────────────────────────────
BuildRequires:  python3
BuildRequires:  python3-module-pip
BuildRequires:  python3-module-pyinstaller

%description
Редактор PDF Альт — приложение для просмотра и редактирования PDF-файлов,
разработанное для операционной системы Альт Рабочая станция.
Позволяет открывать, сохранять, печатать, аннотировать, поворачивать,
удалять и экспортировать страницы PDF-документов.

Разработано ОППО ГИСиСАПР ПУ «СургутАСУнефть», ПАО «Сургутнефтегаз».

%prep
%setup -q

%build
# Install Python dependencies into a local venv so PyInstaller can find them
python3 -m venv .venv
.venv/bin/pip install --quiet \
    PySide6 \
    PyMuPDF

# Run PyInstaller using our spec file (one-file build, no console window)
.venv/bin/pyinstaller \
    --clean \
    --noconfirm \
    --distpath dist \
    --workpath build \
    AltPDF.spec

%install
# Create target directories
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor/256x256/apps

# Install the PyInstaller one-file binary
install -m 755 dist/AltPDF %{buildroot}%{_bindir}/altpdf

# Install help.pdf next to the binary so the app can find it
# (open_help_document() looks in os.path.dirname(sys.executable))
install -m 644 help.pdf %{buildroot}%{_datadir}/%{name}/help.pdf

# Create a wrapper script so the app can locate its own data files
# and so the .desktop file has a stable path
cat > %{buildroot}%{_bindir}/altpdf-wrapper << 'EOF'
#!/bin/sh
# Copy help.pdf next to the binary at first run if not present
HELP_SRC=%{_datadir}/%{name}/help.pdf
HELP_DST=$(dirname $(readlink -f %{_bindir}/altpdf))/help.pdf
[ -f "$HELP_DST" ] || cp "$HELP_SRC" "$HELP_DST" 2>/dev/null || true
exec %{_bindir}/altpdf "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/altpdf-wrapper

# .desktop entry so the app appears in the application menu
cat > %{buildroot}%{_datadir}/applications/%{name}.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Редактор PDF Альт
Name[ru]=Редактор PDF Альт
Comment=Просмотр и редактирование PDF-документов
Comment[ru]=Просмотр и редактирование PDF-документов
Exec=altpdf-wrapper %F
Icon=altpdf
MimeType=application/pdf;
Categories=Office;Viewer;
StartupNotify=true
EOF

# Application icon (convert .ico to .png if imagemagick is available,
# otherwise just copy as-is and rename)
if command -v convert >/dev/null 2>&1; then
    convert icons/icon.ico[0] \
        %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/altpdf.png 2>/dev/null || \
    cp icons/icon.ico \
        %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/altpdf.png
else
    cp icons/icon.ico \
        %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/altpdf.png
fi

%post
# Update the icon cache so the new icon is visible
/usr/bin/gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor 2>/dev/null || true
/usr/bin/update-desktop-database %{_datadir}/applications 2>/dev/null || true

%postun
/usr/bin/gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor 2>/dev/null || true
/usr/bin/update-desktop-database %{_datadir}/applications 2>/dev/null || true

%files
%{_bindir}/altpdf
%{_bindir}/altpdf-wrapper
%{_datadir}/%{name}/help.pdf
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/256x256/apps/altpdf.png

%changelog
* Thu Apr 29 2026 ОППО ГИСиСАПР <dev@sng.ru> - 0.831-alt1
- Initial RPM packaging for Альт Рабочая станция
