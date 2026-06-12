import os
import re


EXT_THEME_ICONS = {
    ".py": "text-x-python",
    ".sh": "application-x-shellscript",
    ".bash": "application-x-shellscript",
    ".zsh": "application-x-shellscript",
    ".pl": "application-x-perl",
    ".rb": "application-x-ruby",
    ".go": "text-x-go",
    ".rs": "text-rust",
    ".c": "text-x-csrc",
    ".h": "text-x-chdr",
    ".cpp": "text-x-c++src",
    ".hpp": "text-x-c++hdr",
    ".java": "text-x-java",
    ".js": "application-javascript",
    ".ts": "application-typescript",
    ".html": "text-html",
    ".htm": "text-html",
    ".css": "text-css",
    ".md": "text-markdown",
    ".rst": "text-x-rst",
    ".txt": "text-x-generic",
    ".log": "text-x-log",
    ".conf": "text-x-generic",
    ".ini": "text-x-generic",
    ".cfg": "text-x-generic",
    ".toml": "text-x-generic",
    ".env": "text-x-generic",
    ".json": "application-json",
    ".xml": "application-xml",
    ".yaml": "application-yaml",
    ".yml": "application-yaml",
    ".png": "image-png",
    ".jpg": "image-jpeg",
    ".jpeg": "image-jpeg",
    ".gif": "image-gif",
    ".bmp": "image-bmp",
    ".svg": "image-svg+xml",
    ".webp": "image-webp",
    ".ico": "image-x-ico",
    ".pdf": "application-pdf",
    ".zip": "application-zip",
    ".tar": "application-x-tar",
    ".gz": "application-gzip",
    ".tgz": "application-gzip",
    ".bz2": "application-x-bzip",
    ".xz": "application-x-xz",
    ".7z": "application-x-7z-compressed",
    ".rar": "application-x-rar",
    ".deb": "application-x-deb",
    ".rpm": "application-x-rpm",
    ".doc": "application-msword",
    ".docx": "application-msword",
    ".xls": "application-vnd.ms-excel",
    ".xlsx": "application-vnd.ms-excel",
    ".ppt": "application-vnd.ms-powerpoint",
    ".pptx": "application-vnd.ms-powerpoint",
    ".mp3": "audio-mpeg",
    ".wav": "audio-x-wav",
    ".flac": "audio-flac",
    ".ogg": "audio-ogg",
    ".mp4": "video-mp4",
    ".mkv": "video-x-matroska",
    ".webm": "video-webm",
    ".avi": "video-x-msvideo",
    ".mov": "video-quicktime",
}

LOCAL_FILENAME_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def safe_local_name(name: str, default: str = "download") -> str:
    cleaned = LOCAL_FILENAME_UNSAFE.sub("_", name or "").strip(" .")
    stem, ext = os.path.splitext(cleaned)
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{stem}_{ext}"
    return cleaned or default


def valid_remote_leaf_name(name: str) -> bool:
    return bool(name) and name not in {".", ".."} and "/" not in name and "\\" not in name
