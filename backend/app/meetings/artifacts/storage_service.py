import os
from pathlib import Path
from typing import Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

LOCAL_ARCHIVE_ROOT = Path("/app/attachments/meetings")


class MeetingStorageService:
    def __init__(self):
        self.bucket = settings.aws_s3_bucket or "gtmprospecting-meeting-artifacts"
        self.region = settings.aws_region or "us-east-1"
        self._s3_client = None

    def _get_client(self):
        if self._s3_client is None:
            kwargs: dict[str, Any] = {"region_name": self.region}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def is_s3_configured(self) -> bool:
        return bool(settings.aws_s3_upload_enabled and settings.aws_region and settings.aws_s3_bucket)

    def generate_s3_key(
        self,
        lead_id: str | None,
        meeting_id: str,
        artifact_type: str,
        filename: str,
    ) -> str:
        lead_part = lead_id or "unassigned"
        return f"gtmprospecting/meetings/{lead_part}/{meeting_id}/{artifact_type}/{filename}"

    def store_bytes(
        self,
        data: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """
        Store artifact bytes in S3 if configured, or fall back to local disk storage.
        Returns dict with s3_bucket, s3_key, and local_path.
        """
        local_path = LOCAL_ARCHIVE_ROOT / s3_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

        if self.is_s3_configured():
            try:
                client = self._get_client()
                client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=data,
                    ContentType=content_type,
                    ServerSideEncryption="AES256",
                )
                return {
                    "s3_bucket": self.bucket,
                    "s3_key": s3_key,
                    "local_path": str(local_path),
                }
            except (BotoCoreError, ClientError) as e:
                # Log and fallback to local file
                return {
                    "s3_bucket": None,
                    "s3_key": s3_key,
                    "local_path": str(local_path),
                    "warning": f"S3 upload failed ({str(e)}), saved locally.",
                }

        return {
            "s3_bucket": None,
            "s3_key": s3_key,
            "local_path": str(local_path),
        }

    def retrieve_bytes(self, s3_key: str, s3_bucket: str | None = None) -> bytes | None:
        """Retrieve artifact bytes from local disk or S3."""
        # 1. Check local file first
        local_path = LOCAL_ARCHIVE_ROOT / s3_key
        if local_path.exists():
            return local_path.read_bytes()

        # 2. Check S3
        bucket = s3_bucket or self.bucket
        if self.is_s3_configured():
            try:
                client = self._get_client()
                resp = client.get_object(Bucket=bucket, Key=s3_key)
                return resp["Body"].read()
            except (BotoCoreError, ClientError):
                return None

        return None

    def generate_presigned_download_url(
        self, s3_key: str, s3_bucket: str | None = None, expires_in: int = 3600
    ) -> str | None:
        """Generate short-lived presigned URL if S3 is active, otherwise local API endpoint."""
        bucket = s3_bucket or self.bucket
        if self.is_s3_configured():
            try:
                client = self._get_client()
                return client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": s3_key},
                    ExpiresIn=expires_in,
                )
            except (BotoCoreError, ClientError):
                pass
        return None


storage_service = MeetingStorageService()
