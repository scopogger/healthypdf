Name:           altpdf
Version:        0.845
Release:        alt1
Summary:        Редактор PDF файлов для Альт Рабочая станция
License:        Proprietary
Group:          Office
URL:            https://sng.ru

Source0:        %{name}-%{version}.tar.gz

# PyInstaller уже включает Python и библиотеки внутри бинарника.
# Нужны только базовые системные библиотеки:
Requires:       libgcc1
Requires:       glibc

# Сборочных зависимостей почти нет — бинарник уже готов
BuildArch:      x86_64

%description
Редактор PDF Альт — приложение для просмотра и редактирования PDF-файлов,
разработанное для операционной системы Альт Рабочая станция.

%prep
%setup -q

%build
# Бинарник уже собран через PyInstaller — дополнительная сборка не нужна

%install
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor/256x256/apps

# Устанавливаем готовый бинарник
install -m 755 dist/AltPDF %{buildroot}%{_bindir}/altpdf

# Устанавливаем help.pdf
install -m 644 help.pdf %{buildroot}%{_datadir}/%{name}/help.pdf

# Скрипт-обёртка (копирует help.pdf рядом с бинарником при первом запуске)
cat > %{buildroot}%{_bindir}/altpdf-wrapper << 'EOF'
#!/bin/sh
HELP_SRC=%{_datadir}/%{name}/help.pdf
HELP_DST=$(dirname $(readlink -f %{_bindir}/altpdf))/help.pdf
[ -f "$HELP_DST" ] || cp "$HELP_SRC" "$HELP_DST" 2>/dev/null || true
exec %{_bindir}/altpdf "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/altpdf-wrapper

# Ярлык в меню приложений
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

# Иконка
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
* Thu May 26 2026 ОППО ГИСиСАПР <dev@sng.ru> - 0.845-alt1
- New features and bug fixes based on testing feedback

* Thu May 22 2026 ОППО ГИСиСАПР <dev@sng.ru> - 0.842-alt1
- New features and bug fixes based on testing feedback

* Thu May 19 2026 ОППО ГИСиСАПР <dev@sng.ru> - 0.841-alt1
- Minor bug fixes and improvements

* Thu Apr 29 2026 ОППО ГИСиСАПР <dev@sng.ru> - 0.831-alt1
- Initial RPM packaging for Альт Рабочая станция
