import logging
import os
import posixpath

import paramiko
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from widgets.sftp_transfer import TransferThread as _TransferThread
from widgets.sftp_utils import format_size as _format_size, valid_remote_leaf_name as _valid_remote_leaf_name

log = logging.getLogger(__name__)


class SftpTransferOpsMixin:
    def _upload(self) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        locals_, _ = QFileDialog.getOpenFileNames(self, "Upload files", "")
        if not locals_:
            return
        queue = self._resolve_upload_conflicts([
            (local, posixpath.join(self.cwd, os.path.basename(local)))
            for local in locals_
        ])
        if not queue:
            return
        self._start_transfer("upload", queue[0][0], queue[0][1])
        self._upload_queue.extend(queue[1:])
        for local, remote in queue[1:]:
            self._add_queued_transfer("upload", local, remote)

    def _upload_folder(self) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        local = QFileDialog.getExistingDirectory(self, "Upload folder", "")
        if not local:
            return
        remote = posixpath.join(self.cwd, os.path.basename(local))
        queue = self._resolve_upload_conflicts([(local, remote)])
        if not queue:
            return
        self._start_transfer("upload", queue[0][0], queue[0][1])

    def _new_folder(self) -> None:
        if self.sftp is None:
            return
        name, ok = QInputDialog.getText(self, "New remote folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        if not _valid_remote_leaf_name(name):
            QMessageBox.warning(self, "Invalid folder name", "Enter a single folder name.")
            return
        try:
            self.sftp.mkdir(posixpath.join(self.cwd, name))
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "New folder failed", str(e))
            return
        self._refresh()


    def _download(self) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        selected = self._selected_remote_items()
        if not selected:
            QMessageBox.information(self, "SFTP", "Select one or more remote items to download.")
            return
        self._download_remote_items(selected)

    def _start_transfer(self, mode: str, local: str, remote: str) -> None:
        if self.sftp is None:
            return
        if not local or not remote:
            return
        self._last_transfer_failed = False
        self._begin_transfer_progress(mode, local, remote)
        self._set_buttons_enabled(False)
        self._mark_transfer_active(mode, local, remote)

        t = _TransferThread(self.sftp, mode, local, remote)
        t.progress.connect(self._on_transfer_progress)
        t.finished_ok.connect(self._on_transfer_done)
        t.failed.connect(self._on_transfer_failed)
        t.cancelled.connect(self._on_transfer_cancelled)
        self._transfer = t
        t.finished.connect(lambda _transfer=t: self._cleanup_transfer(_transfer))
        self.cancel_btn.setEnabled(True)
        t.start()

    def _cancel_transfer(self) -> None:
        if self._transfer is not None:
            self._transfer.cancel()
            self.cancel_btn.setEnabled(False)
            self.transfer_status.setText("Cancelling transfer...")
            self._last_transfer_cancelled = True
            self._mark_transfer_finished("Canceled")
            if self.sftp is not None:
                try:
                    self.sftp.close()
                except Exception:
                    log.debug("sftp close during transfer cancel failed", exc_info=True)
                self.sftp = None
            QTimer.singleShot(
                3000,
                lambda transfer=self._transfer: self._finish_stuck_cancelled_transfer(transfer),
            )

    def _stop_transfer(self, wait: bool = False) -> None:
        transfer = self._transfer
        if transfer is None:
            return
        transfer.cancel()
        if wait and transfer.isRunning():
            if self.sftp is not None:
                try:
                    self.sftp.close()
                except Exception:
                    log.debug("sftp close during transfer stop failed", exc_info=True)
            transfer.wait(2000)
        self._transfer = None
        self.cancel_btn.setEnabled(False)

    def _finish_stuck_cancelled_transfer(self, transfer: _TransferThread | None) -> None:
        if transfer is None or transfer is not self._transfer:
            return
        if not transfer.isRunning():
            return
        log.warning("SFTP transfer did not stop after cancel; detaching UI from worker")
        self._disconnect_transfer_signals(transfer)
        self._transfer = None
        self._last_transfer_cancelled = False
        self.cancel_btn.setEnabled(False)
        self._reset_transfer_progress()
        self._mark_transfer_finished("Canceled")
        if not self._detaching:
            self._reopen_sftp_after_cancel()

    def _disconnect_transfer_signals(self, transfer: _TransferThread) -> None:
        for signal, slot in (
            (transfer.progress, self._on_transfer_progress),
            (transfer.finished_ok, self._on_transfer_done),
            (transfer.failed, self._on_transfer_failed),
            (transfer.cancelled, self._on_transfer_cancelled),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _on_transfer_progress(self, done: int, total: int) -> None:
        self._update_transfer_progress(done, total)

    def _begin_transfer_progress(self, mode: str, local: str, remote: str) -> None:
        self._transfer_mode = mode
        self._transfer_name = (
            os.path.basename(local) if mode == "upload" else posixpath.basename(remote)
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.transfer_panel.show()
        self._update_transfer_progress(0, 0)

    def _update_transfer_progress(self, done: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, int(done * 100 / total)))
            size_text = f"{_format_size(done)} / {_format_size(total)}"
        else:
            percent = 0
            size_text = _format_size(done)
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}%")

        action = "Uploading" if self._transfer_mode == "upload" else "Downloading"
        if self._transfer_name:
            self.transfer_status.setText(f"{action} {self._transfer_name}  -  {size_text}")
        else:
            self.transfer_status.setText(f"{action}  -  {size_text}")

    def _reset_transfer_progress(self) -> None:
        self._transfer_mode = None
        self._transfer_name = ""
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.transfer_status.clear()
        self.transfer_panel.hide()

    def _on_transfer_done(self, message: str) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("100%")
        self.transfer_status.setText(message)
        self.transfer_panel.show()
        self._mark_transfer_finished("Done")
        self.path_label.setText(f"{self.cwd}   ·   {message}")
        self._refresh()

    def _on_transfer_failed(self, message: str) -> None:
        self._last_transfer_failed = True
        self.transfer_status.setText(f"Transfer failed: {message}")
        self.transfer_panel.show()
        self._mark_transfer_finished("Failed")
        QMessageBox.warning(self, "SFTP transfer failed", message)

    def _on_transfer_cancelled(self, message: str) -> None:
        self._last_transfer_cancelled = True
        self.transfer_status.setText(message)
        self.transfer_panel.show()
        self._mark_transfer_finished("Canceled")

    def _cleanup_transfer(self, transfer: _TransferThread | None = None) -> None:
        if transfer is not None and transfer is not self._transfer:
            return
        self._set_buttons_enabled(True)
        self._transfer = None
        self._reset_transfer_progress()
        if self._last_transfer_cancelled:
            self._last_transfer_cancelled = False
            if not self._detaching:
                self._reopen_sftp_after_cancel()
            return
        if self._last_transfer_failed:
            self._last_transfer_failed = False
            return
        if self._download_queue and self.sftp is not None:
            local, remote = self._download_queue.pop(0)
            self._remove_queued_transfer(local, remote)
            self._start_transfer("download", local, remote)
            return
        # Chain into the next queued upload (drag-and-drop with multiple files).
        if self._upload_queue and self.sftp is not None:
            local, remote = self._upload_queue.pop(0)
            self._remove_queued_transfer(local, remote)
            self._start_transfer("upload", local, remote)

    def _reopen_sftp_after_cancel(self) -> None:
        if self._ssh_client is None:
            self._set_buttons_enabled(False)
            return
        try:
            self.sftp = self._ssh_client.open_sftp()
        except (OSError, paramiko.SSHException) as e:
            log.warning("failed to reopen SFTP after transfer cancel: %s", e)
            self.sftp = None
            self.path_label.setText(f"SFTP unavailable after cancel: {e}")
            self._set_buttons_enabled(False)
            return
        self._set_buttons_enabled(True)
        self._refresh()

    def closeEvent(self, event) -> None:
        self._stop_transfer(wait=True)
        super().closeEvent(event)
