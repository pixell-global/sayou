import pathlib

from sayou.storage.s3 import StorageService


class LocalStorage(StorageService):
    """Filesystem-backed storage for zero-config local dev.

    Stores files at {base_path}/{org_id}/sayou/{workspace_id}/v/{version_id}.
    No S3 credentials required.
    """

    def __init__(self, base_path: str = "~/.sayou/storage"):
        self._base = pathlib.Path(base_path).expanduser()
        self._client = None
        self._client_cm = None

    async def upload_version(
        self,
        content: bytes,
        org_id: str,
        workspace_id: str,
        version_id: str,
    ) -> tuple[str, str, int, str]:
        """Write content to local filesystem."""
        s3_key = self.generate_key(org_id, workspace_id, version_id)
        content_hash = self.calculate_checksum(content)
        size_bytes = len(content)

        file_path = self._base / s3_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        return s3_key, "local", size_bytes, content_hash

    async def download_version(self, s3_key: str, bucket: str | None = None) -> bytes:
        """Read content from local filesystem."""
        file_path = self._base / s3_key
        return file_path.read_bytes()

    async def ensure_bucket(self) -> None:
        self._base.mkdir(parents=True, exist_ok=True)

    async def close(self) -> None:
        pass
