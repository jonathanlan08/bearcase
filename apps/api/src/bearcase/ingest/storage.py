"""Storage abstraction. Keys are generated server-side; user filenames never become paths."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from bearcase.config import get_settings


def make_object_key(deal_id: uuid.UUID, document_id: uuid.UUID, version_no: int, sha256: str, extension: str) -> str:
    return f"deals/{deal_id}/documents/{document_id}/v{version_no}/{sha256[:16]}.{extension}"


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key escapes the storage root")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3Storage:
    """S3-compatible backend (AWS S3, MinIO). Requires the optional boto3 dependency."""

    def __init__(self, bucket: str, endpoint_url: str | None = None, region: str | None = None):
        import boto3  # type: ignore[import-not-found]

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class MemoryStorage:
    """Test adapter."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.blobs[key] = data

    def get(self, key: str) -> bytes:
        return self.blobs[key]

    def exists(self, key: str) -> bool:
        return key in self.blobs

    def delete(self, key: str) -> None:
        self.blobs.pop(key, None)


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            if not s.s3_bucket:
                raise RuntimeError("BEARCASE_S3_BUCKET is required for the s3 storage backend")
            _storage = S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
        else:
            _storage = LocalStorage(s.storage_local_dir)
    return _storage


def set_storage(backend: StorageBackend | None) -> None:
    global _storage
    _storage = backend
