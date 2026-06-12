import os
import posixpath

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTreeWidgetItem


class SftpTransferQueueMixin:
    def _add_queued_transfer(self, mode: str, local: str, remote: str) -> None:
        item = QTreeWidgetItem(self.transfer_queue, [
            "Queued",
            "Upload" if mode == "upload" else "Download",
            os.path.basename(local) if mode == "upload" else posixpath.basename(remote),
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "mode": mode,
            "local": local,
            "remote": remote,
            "status": "Queued",
        })
        self.transfer_queue.show()

    def _mark_transfer_active(self, mode: str, local: str, remote: str) -> None:
        self._remove_queued_transfer(local, remote)
        item = QTreeWidgetItem(self.transfer_queue, [
            "Active",
            "Upload" if mode == "upload" else "Download",
            os.path.basename(local) if mode == "upload" else posixpath.basename(remote),
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "mode": mode,
            "local": local,
            "remote": remote,
            "status": "Active",
        })
        self._active_transfer_row = item
        self.transfer_queue.show()

    def _mark_transfer_finished(self, status: str) -> None:
        item = self._active_transfer_row
        if item is None:
            return
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        meta["status"] = status
        item.setData(0, Qt.ItemDataRole.UserRole, meta)
        item.setText(0, status)
        self._active_transfer_row = None
        self.transfer_queue.show()

    def _remove_queued_transfer(self, local: str, remote: str) -> None:
        root = self.transfer_queue.invisibleRootItem()
        for i in range(root.childCount() - 1, -1, -1):
            item = root.child(i)
            meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if (
                meta.get("status") == "Queued"
                and meta.get("local") == local
                and meta.get("remote") == remote
            ):
                root.removeChild(item)

    def _show_transfer_context_menu(self, pos) -> None:
        item = self.transfer_queue.itemAt(pos)
        if item is None:
            return
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        menu = QMenu(self)
        if meta.get("status") == "Failed":
            retry = menu.addAction("Retry transfer")
            retry.triggered.connect(lambda: self._retry_transfer(meta))
        if meta.get("status") == "Active":
            cancel = menu.addAction("Cancel transfer")
            cancel.triggered.connect(self._cancel_transfer)
        clear = menu.addAction("Clear row")
        clear.triggered.connect(lambda: self.transfer_queue.invisibleRootItem().removeChild(item))
        menu.exec(self.transfer_queue.mapToGlobal(pos))

    def _retry_transfer(self, meta: dict) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        local = meta.get("local", "")
        remote = meta.get("remote", "")
        if not local or not remote:
            return
        self._start_transfer(meta.get("mode", "upload"), local, remote)
