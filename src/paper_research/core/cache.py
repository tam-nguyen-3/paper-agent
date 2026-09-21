"""Atomic, parameter-keyed storage for a single local process."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

DEFAULT_WORKSPACE = "research_data"


class Cache:
    def __init__(self, workspace_dir=DEFAULT_WORKSPACE):
        self.root = Path(workspace_dir).resolve()

    @staticmethod
    def key(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def path(self, namespace, key, suffix=".json"):
        return self.root / namespace / (self.key(key) + suffix)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, namespace, key, ttl=86400):
        path = self.path(namespace, key)
        try:
            if ttl is not None and time.time() - path.stat().st_mtime >= ttl:
                return None
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def put(self, namespace, key, value):
        self.write(
            self.path(namespace, key), json.dumps(value, ensure_ascii=False).encode()
        )

    def artifact(self, namespace, key, text):
        path = self.path(namespace, key, ".md")
        self.write(path, text.encode())
        return "/" + path.relative_to(self.root).as_posix()
