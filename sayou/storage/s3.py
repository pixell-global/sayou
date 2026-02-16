import hashlib

try:
    import aioboto3
except ImportError:
    aioboto3 = None

from sayou.config import settings


class StorageService:
    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        self.bucket = bucket or settings.s3_bucket_name
        self.region = region or settings.s3_region
        self.endpoint_url = endpoint_url or settings.s3_endpoint_url
        self.access_key_id = access_key_id or settings.s3_access_key_id
        self.secret_access_key = secret_access_key or settings.s3_secret_access_key
        if aioboto3 is None:
            raise ImportError(
                "S3 storage requires additional dependencies. "
                "Install with: pip install sayou[s3]"
            )
        self._session = aioboto3.Session()
        self._client = None
        self._client_cm = None

    async def _get_client(self):
        """Lazily initialize and return a persistent S3 client."""
        if self._client is None:
            self._client_cm = self._session.client(**self._client_config())
            self._client = await self._client_cm.__aenter__()
        return self._client

    async def close(self):
        """Close the persistent S3 client."""
        if self._client_cm is not None:
            await self._client_cm.__aexit__(None, None, None)
            self._client = None
            self._client_cm = None

    def _client_config(self) -> dict:
        config = {
            "service_name": "s3",
            "region_name": self.region,
        }
        if self.access_key_id:
            config["aws_access_key_id"] = self.access_key_id
        if self.secret_access_key:
            config["aws_secret_access_key"] = self.secret_access_key
        if self.endpoint_url:
            config["endpoint_url"] = self.endpoint_url
        return config

    @staticmethod
    def generate_key(org_id: str, workspace_id: str, version_id: str) -> str:
        return f"{org_id}/sayou/{workspace_id}/v/{version_id}"

    @staticmethod
    def calculate_checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def upload_version(
        self,
        content: bytes,
        org_id: str,
        workspace_id: str,
        version_id: str,
        content_type: str = "text/markdown",
    ) -> tuple[str, str, int, str]:
        """Upload content and return (s3_key, bucket, size_bytes, content_hash)."""
        s3_key = self.generate_key(org_id, workspace_id, version_id)
        content_hash = self.calculate_checksum(content)
        size_bytes = len(content)

        client = await self._get_client()
        await client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=content,
            ContentType=content_type,
        )

        return s3_key, self.bucket, size_bytes, content_hash

    async def download_version(self, s3_key: str, bucket: str | None = None) -> bytes:
        """Download content from S3."""
        bucket = bucket or self.bucket
        client = await self._get_client()
        response = await client.get_object(Bucket=bucket, Key=s3_key)
        content = await response["Body"].read()
        return content

    async def ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist (for MinIO bootstrap)."""
        client = await self._get_client()
        try:
            await client.head_bucket(Bucket=self.bucket)
        except Exception:
            await client.create_bucket(
                Bucket=self.bucket,
                CreateBucketConfiguration={"LocationConstraint": self.region},
            )
