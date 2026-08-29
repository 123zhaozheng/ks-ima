"""Object storage client with private, bounded S3-compatible operations."""

from __future__ import annotations

import base64
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, BinaryIO, cast
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from ima.config import Settings


class StorageClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ObjectStorageClient:
    """Synchronous boto client used only from explicit application/task boundaries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not self.enabled:
            self._client = None
            return
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key_id.get_secret_value()
            if settings.storage_access_key_id
            else None,
            aws_secret_access_key=settings.storage_secret_access_key.get_secret_value()
            if settings.storage_secret_access_key
            else None,
            config=Config(
                connect_timeout=settings.storage_connect_timeout_seconds,
                read_timeout=settings.storage_read_timeout_seconds,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.settings.storage_endpoint and self.settings.storage_bucket)

    def object_key(self, document_id: UUID, version: int) -> str:
        return str(PurePosixPath("documents") / str(document_id) / str(version) / "source")

    def presigned_put(self, key: str, checksum: str, size_bytes: int, mime_type: str) -> str:
        client = self._require_client()
        try:
            return str(
                client.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self.settings.storage_bucket,
                        "Key": key,
                        "ChecksumSHA256": self._checksum_header(checksum),
                        "ContentType": mime_type,
                    },
                    ExpiresIn=self.settings.storage_presign_seconds,
                    HttpMethod="PUT",
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("STORAGE_UNAVAILABLE") from exc

    def presigned_get(
        self, key: str, filename: str, mime_type: str, *, inline: bool = False
    ) -> str:
        client = self._require_client()
        disposition = "inline" if inline else "attachment"
        safe_name = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
        try:
            return str(
                client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.settings.storage_bucket,
                        "Key": key,
                        "ResponseContentType": mime_type,
                        "ResponseContentDisposition": f'{disposition}; filename="{safe_name}"',
                    },
                    ExpiresIn=self.settings.storage_presign_seconds,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("STORAGE_UNAVAILABLE") from exc

    def verify(self, key: str, checksum: str, size_bytes: int, mime_type: str) -> None:
        client = self._require_client()
        try:
            response = client.head_object(
                Bucket=self.settings.storage_bucket,
                Key=key,
                ChecksumMode="ENABLED",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("OBJECT_MISSING") from exc
        actual_checksum = response.get("ChecksumSHA256")
        if response.get("ContentLength") != size_bytes or actual_checksum != self._checksum_header(
            checksum
        ):
            raise StorageClientError("OBJECT_VERIFICATION_FAILED")
        actual_mime = response.get("ContentType", "").split(";", 1)[0].lower()
        if actual_mime != mime_type.lower():
            raise StorageClientError("OBJECT_VERIFICATION_FAILED")

    def read(self, key: str) -> BinaryIO:
        client = self._require_client()
        try:
            response = client.get_object(Bucket=self.settings.storage_bucket, Key=key)
            return cast(BinaryIO, response["Body"])
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("OBJECT_MISSING") from exc

    def copy_verified(
        self, source_key: str, target_key: str, checksum: str, size_bytes: int, mime_type: str
    ) -> None:
        client = self._require_client()
        try:
            source = client.get_object(
                Bucket=self.settings.storage_bucket, Key=source_key, ChecksumMode="ENABLED"
            )
            body = cast(BinaryIO, source["Body"])
            digest, actual_size = self.bounded_digest(body)
            if digest != checksum or actual_size != size_bytes:
                raise StorageClientError("SOURCE_OBJECT_CHANGED")
            client.copy_object(
                Bucket=self.settings.storage_bucket,
                Key=target_key,
                CopySource={"Bucket": self.settings.storage_bucket, "Key": source_key},
                ContentType=mime_type,
                MetadataDirective="REPLACE",
                ChecksumAlgorithm="SHA256",
            )
            self.verify(target_key, checksum, size_bytes, mime_type)
        except StorageClientError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("STORAGE_UNAVAILABLE") from exc

    def delete(self, key: str) -> None:
        client = self._require_client()
        try:
            client.delete_object(Bucket=self.settings.storage_bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("STORAGE_UNAVAILABLE") from exc

    def list_keys(self, prefix: str, *, max_keys: int = 10000) -> list[str]:
        """List object keys under a prefix, bounded for verification reports."""
        client = self._require_client()
        keys: list[str] = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self.settings.storage_bucket,
                Prefix=prefix,
                PaginationConfig={"PageSize": 1000, "MaxItems": max_keys},
            )
            for page in pages:
                keys.extend(str(item["Key"]) for item in page.get("Contents", []))
        except (BotoCoreError, ClientError) as exc:
            raise StorageClientError("STORAGE_UNAVAILABLE") from exc
        return keys

    def bounded_digest(self, body: BinaryIO) -> tuple[str, int]:
        digest = sha256()
        total = 0
        while chunk := body.read(65536):
            total += len(chunk)
            if total > self.settings.storage_max_object_bytes:
                raise StorageClientError("OBJECT_TOO_LARGE")
            digest.update(chunk)
        return digest.hexdigest(), total

    @staticmethod
    def _checksum_header(checksum: str) -> str:
        return base64.b64encode(bytes.fromhex(checksum)).decode("ascii")

    def _require_client(self) -> Any:
        if self._client is None:
            raise StorageClientError("STORAGE_UNAVAILABLE")
        return cast(Any, self._client)
