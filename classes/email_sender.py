import os
import sys
import subprocess
from urllib.parse import quote

from PySide6.QtWidgets import QMessageBox


def _clean_subprocess_env() -> dict:
    """Return os.environ with LD_LIBRARY_PATH restored to its pre-PyInstaller
    value so that system processes (xdg-email, evolution, kde-open, …) do not
    accidentally load our bundled Qt libraries instead of the system ones.
    PyInstaller saves the original value as LD_LIBRARY_PATH_ORIG."""
    env = os.environ.copy()
    if sys.platform.startswith("linux"):
        if 'LD_LIBRARY_PATH_ORIG' in env:
            env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
        else:
            env.pop('LD_LIBRARY_PATH', None)
    return env


class EmailSender:
    """
    Opens the platform's default mail client with *file_path* pre-attached.

    Usage:
        ok = EmailSender.send(parent_widget, file_path)
    """

    @staticmethod
    def send(parent, file_path: str) -> bool:
        """
        Try to open a new mail draft with *file_path* attached.
        Returns True if the client was launched without an obvious errors.
        """
        if not os.path.isfile(file_path):
            QMessageBox.warning(parent, "Ошибка", f"Файл не найден:\n{file_path}")
            return False

        subject = os.path.basename(file_path)
        body = f"В приложении PDF документ: {subject}"

        if sys.platform == "win32":
            return EmailSender._send_windows(parent, file_path, subject, body)
        else:
            return EmailSender._send_linux(parent, file_path, subject, body)

    # ------------------------------------------------------------------ #
    #  Windows                                                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _send_windows(parent, file_path: str, subject: str, body: str) -> bool:
        """
        Primary:  Outlook COM automation — opens a draft, attaches the file,
                  and displays the compose window.  User can edit & send.
        Fallback: xdg-email / webbrowser mailto: (no attachment possible on
                  non-Outlook clients, so we warn the user).
        """
        try:
            import win32com.client as win32
            ol = win32.Dispatch("Outlook.Application")
            mail = ol.CreateItem(0)  # 0 = olMailItem
            mail.Subject = subject
            mail.Body = body
            mail.Attachments.Add(file_path)
            mail.Display()  # show compose window; don't auto-send
            return True
        except Exception as e:
            print(f"[EmailSender] Outlook COM failed: {e}")

        # Outlook unavailable — fall back to mailto: (no attachment)
        return EmailSender._send_mailto_fallback(parent, file_path, subject, body)

    # ------------------------------------------------------------------ #
    #  Linux                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _send_linux(parent, file_path: str, subject: str, body: str) -> bool:
        """
        Try strategies in order, stop at the first success.

        1. evolution --component=mail mailto:  with attach= in the URI
        2. xdg-email --attach  (freedesktop standard; works with Evolution,
                                Thunderbird, R7 Organiser when registered)
        3. R7 Organiser direct call (same mailto URI style)
        4. mailto: fallback via xdg-open / webbrowser (no attachment)

        All subprocess calls receive a cleaned environment so that
        PyInstaller's LD_LIBRARY_PATH (pointing at the bundled Qt) is not
        inherited by system processes.
        """
        env = _clean_subprocess_env()

        # 1 -- Evolution directly
        evolution = EmailSender._find_binary(
            ["evolution", "/usr/bin/evolution", "/usr/local/bin/evolution"]
        )
        if evolution:
            try:
                # Evolution understands attach= inside the mailto URI
                uri = (
                    f"mailto:?subject={quote(subject)}"
                    f"&body={quote(body)}"
                    f"&attach={quote('file://' + file_path)}"
                )
                subprocess.Popen(
                    [evolution, "--component=mail", uri],
                    start_new_session=True,
                    env=env,
                )
                return True
            except Exception as e:
                print(f"[EmailSender] Evolution failed: {e}")

        # 2 -- xdg-email (best option: handles attachment portably)
        if EmailSender._which("xdg-email"):
            try:
                cmd = [
                    "xdg-email",
                    "--subject", subject,
                    "--body", body,
                    "--attach", file_path,
                ]
                result = subprocess.run(
                    cmd,
                    timeout=10,
                    start_new_session=True,
                    env=env,
                )
                if result.returncode == 0:
                    return True
                print(f"[EmailSender] xdg-email exited with code {result.returncode}")
            except Exception as e:
                print(f"[EmailSender] xdg-email failed: {e}")

        # 3 -- R7 Organiser
        r7 = EmailSender._find_binary([
            "/opt/r7-office/organizer/r7organizer",
            "/opt/r7office/organizer/r7organizer",
        ])
        if r7:
            try:
                uri = (
                    f"mailto:?subject={quote(subject)}"
                    f"&body={quote(body)}"
                    f"&attach={quote('file://' + file_path)}"
                )
                subprocess.Popen([r7, uri], start_new_session=True, env=env)
                return True
            except Exception as e:
                print(f"[EmailSender] R7 Organiser failed: {e}")

        # 4 -- mailto: fallback (no attachment)
        return EmailSender._send_mailto_fallback(parent, file_path, subject, body)

    # ------------------------------------------------------------------ #
    #  Fallback – mailto: without attachment                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _send_mailto_fallback(parent, file_path: str, subject: str, body: str) -> bool:
        """
        Opens a bare mailto: link (no attachment support).
        Informs the user where the file is so they can attach it manually.
        """
        import webbrowser
        mailto = f"mailto:?subject={quote(subject)}&body={quote(body)}"
        try:
            # webbrowser.open() spawns a child process and doesn't accept an
            # env argument.  Temporarily restore LD_LIBRARY_PATH in the
            # *current* process environment so the spawned browser inherits
            # the correct value, then put it back afterwards.
            _old = os.environ.get('LD_LIBRARY_PATH')
            _orig = os.environ.get('LD_LIBRARY_PATH_ORIG')
            try:
                if sys.platform.startswith('linux'):
                    if _orig is not None:
                        os.environ['LD_LIBRARY_PATH'] = _orig
                    else:
                        os.environ.pop('LD_LIBRARY_PATH', None)
                webbrowser.open(mailto)
            finally:
                if _old is not None:
                    os.environ['LD_LIBRARY_PATH'] = _old
                else:
                    os.environ.pop('LD_LIBRARY_PATH', None)
        except Exception as e:
            print(f"[EmailSender] webbrowser.open failed: {e}")
            QMessageBox.critical(
                parent,
                "Ошибка",
                f"Не удалось открыть почтовый клиент.\n\n"
                f"Прикрепите файл вручную:\n{file_path}",
            )
            return False

        # mailto opened, but we couldn't attach — tell the user
        QMessageBox.information(
            parent,
            "Вложение к письму",
            f"Почтовый клиент открыт, но файл не удалось прикрепить автоматически.\n\n"
            f"Прикрепите файл вручную:\n{file_path}",
        )
        return True

    # ------------------------------------------------------------------ #
    #  Helpers                                                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _which(name: str) -> bool:
        """True if *name* is found on PATH."""
        import shutil
        return shutil.which(name) is not None

    @staticmethod
    def _find_binary(candidates: list) -> str | None:
        """Return the first existing path from *candidates*, or None."""
        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None
