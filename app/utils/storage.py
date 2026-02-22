from __future__ import annotations

import os
import uuid

from app.config import settings


def ensure_storage_dir() -> str:
    path = settings.STORAGE_PATH
    os.makedirs(path, exist_ok=True)
    return path


def save_upload(*, filename: str, content: bytes) -> str:
    """Save to local storage. Returns file_url/path."""
    if settings.STORAGE_TYPE != "local":
        raise NotImplementedError("Only local storage is implemented in priority 1-7")

    root = ensure_storage_dir()
    ext = ""
    if "." in filename:
        ext = "." + filename.split(".")[-1]
    key = f"{uuid.uuid4()}{ext}"
    path = os.path.join(root, key)
    with open(path, "wb") as f:
        f.write(content)
    return path
