import os
import posixpath

from PyQt6.QtCore import Qt


class SftpDropMixin:
    def _target_dir_for_drop(self, pos) -> str:
        """If the drop landed on a directory row, upload into that directory;
        otherwise use the current cwd. Used by dropEvent (and a unit test)."""
        tree_pos = self.tree.mapFrom(self, pos)
        item = self.tree.itemAt(tree_pos)
        if item is None:
            return self.cwd
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("is_dir") and meta.get("name"):
            return posixpath.join(self.cwd, meta["name"])
        return self.cwd

    def dragEnterEvent(self, event) -> None:
        if self.sftp is None:
            event.ignore()
            return
        md = event.mimeData()
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        # Same gate as dragEnter — many platforms only consult this one once a
        # drag is already inside.
        if self.sftp is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if self.sftp is None:
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            event.ignore()
            return

        target_dir = self._target_dir_for_drop(event.position().toPoint())

        # Queue both files and folders; folders upload recursively.
        upload_items: list[str] = []
        for p in paths:
            if os.path.isdir(p) or os.path.isfile(p):
                upload_items.append(p)

        if not upload_items:
            event.acceptProposedAction()
            return

        # Build the upload queue. If nothing's transferring, kick off the first
        # immediately; the rest chain via _cleanup_transfer.
        new_queue = self._resolve_upload_conflicts([
            (local, posixpath.join(target_dir, os.path.basename(local)))
            for local in upload_items
        ])
        if not new_queue:
            event.acceptProposedAction()
            return
        if self._transfer is not None:
            self._upload_queue.extend(new_queue)
            for local, remote in new_queue:
                self._add_queued_transfer("upload", local, remote)
        else:
            first_local, first_remote = new_queue[0]
            self._upload_queue.extend(new_queue[1:])
            for local, remote in new_queue[1:]:
                self._add_queued_transfer("upload", local, remote)
            self._start_transfer("upload", first_local, first_remote)

        event.acceptProposedAction()
