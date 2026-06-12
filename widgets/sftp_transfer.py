import logging
import os
import posixpath
import stat

import paramiko
from PyQt6.QtCore import QThread, pyqtSignal

from widgets.sftp_utils import safe_local_name

log = logging.getLogger(__name__)


class TransferThread(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal(str)

    def __init__(self, sftp: paramiko.SFTPClient, mode: str, local_path: str, remote_path: str):
        super().__init__()
        self.sftp = sftp
        self.mode = mode
        self.local_path = local_path
        self.remote_path = remote_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self):
        try:
            if self.mode == "upload":
                self._run_upload()
            else:
                self._run_download()
        except (EOFError, OSError, paramiko.SSHException) as e:
            if self._cancelled:
                self.cancelled.emit("Transfer cancelled")
            else:
                log.exception("SFTP transfer failed")
                self.failed.emit(str(e) or e.__class__.__name__)

    def _run_upload(self) -> None:
        if os.path.isdir(self.local_path):
            total = self._local_size(self.local_path)
            self._emit_progress(0, total)
            done = self._upload_dir(self.local_path, self.remote_path, 0, total)
            self._emit_progress(done, total)
            self._raise_if_cancelled()
            self.finished_ok.emit(f"Uploaded folder {os.path.basename(self.local_path)}")
        else:
            self.sftp.put(self.local_path, self.remote_path, callback=self._callback)
            self._raise_if_cancelled()
            self.finished_ok.emit(f"Uploaded {os.path.basename(self.local_path)}")

    def _run_download(self) -> None:
        if self._remote_is_dir(self.remote_path):
            total = self._remote_size(self.remote_path)
            self._emit_progress(0, total)
            done = self._download_dir(self.remote_path, self.local_path, 0, total)
            self._emit_progress(done, total)
            self._raise_if_cancelled()
            self.finished_ok.emit(f"Downloaded folder {posixpath.basename(self.remote_path)}")
        else:
            self.sftp.get(self.remote_path, self.local_path, callback=self._callback)
            self._raise_if_cancelled()
            self.finished_ok.emit(f"Downloaded {posixpath.basename(self.remote_path)}")

    def _callback(self, done: int, total: int):
        self._raise_if_cancelled()
        self.progress.emit(done, total)

    def _emit_progress(self, done: int, total: int) -> None:
        self._raise_if_cancelled()
        self.progress.emit(done, total)

    def _raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise OSError("Transfer cancelled")

    def _mkdir_if_missing(self, remote_path: str) -> None:
        try:
            self.sftp.mkdir(remote_path)
        except OSError:
            pass

    def _local_size(self, local_path: str) -> int:
        if os.path.isfile(local_path):
            return os.path.getsize(local_path)
        total = 0
        for root, _dirs, files in os.walk(local_path):
            for name in files:
                path = os.path.join(root, name)
                try:
                    total += os.path.getsize(path)
                except OSError:
                    log.debug("could not stat %s", path, exc_info=True)
        return total

    def _remote_is_dir(self, remote_path: str) -> bool:
        attr = self.sftp.stat(remote_path)
        return stat.S_ISDIR(attr.st_mode or 0)

    def _remote_size(self, remote_path: str) -> int:
        attr = self.sftp.stat(remote_path)
        if not stat.S_ISDIR(attr.st_mode or 0):
            return attr.st_size or 0
        total = 0
        for child in self.sftp.listdir_attr(remote_path):
            if child.filename in (".", ".."):
                continue
            child_path = posixpath.join(remote_path, child.filename)
            if stat.S_ISDIR(child.st_mode or 0):
                total += self._remote_size(child_path)
            else:
                total += child.st_size or 0
        return total

    def _upload_dir(self, local_dir: str, remote_dir: str, done: int, total: int) -> int:
        self._raise_if_cancelled()
        self._mkdir_if_missing(remote_dir)
        for name in sorted(os.listdir(local_dir)):
            self._raise_if_cancelled()
            local_child = os.path.join(local_dir, name)
            remote_child = posixpath.join(remote_dir, name)
            if os.path.isdir(local_child):
                done = self._upload_dir(local_child, remote_child, done, total)
            elif os.path.isfile(local_child):
                base = done

                def callback(sent: int, _file_total: int, base=base):
                    self._emit_progress(base + sent, total)

                self.sftp.put(local_child, remote_child, callback=callback)
                done += os.path.getsize(local_child)
                self._emit_progress(done, total)
        return done

    def _download_dir(self, remote_dir: str, local_dir: str, done: int, total: int) -> int:
        self._raise_if_cancelled()
        os.makedirs(local_dir, exist_ok=True)
        for child in sorted(self.sftp.listdir_attr(remote_dir), key=lambda a: a.filename.lower()):
            self._raise_if_cancelled()
            if child.filename in (".", ".."):
                continue
            remote_child = posixpath.join(remote_dir, child.filename)
            local_child = os.path.join(local_dir, safe_local_name(child.filename))
            if stat.S_ISDIR(child.st_mode or 0):
                done = self._download_dir(remote_child, local_child, done, total)
            else:
                base = done

                def callback(received: int, _file_total: int, base=base):
                    self._emit_progress(base + received, total)

                self.sftp.get(remote_child, local_child, callback=callback)
                done += child.st_size or 0
                self._emit_progress(done, total)
        return done
