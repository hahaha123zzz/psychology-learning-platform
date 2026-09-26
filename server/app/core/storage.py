import asyncio
import hashlib
from datetime import timedelta
from functools import lru_cache

import boto3
from botocore.config import Config
from minio import Minio

from app.core.config import get_settings


@lru_cache
def get_storage_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


@lru_cache
def get_s3_client():
    settings = get_settings()
    protocol = "https" if settings.minio_secure else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{protocol}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def ensure_bucket_sync() -> str:
    client = get_storage_client()
    settings = get_settings()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    return settings.minio_bucket


async def ensure_bucket() -> str:
    return await asyncio.to_thread(ensure_bucket_sync)


def put_object_sync(*, key: str, data, length: int, content_type: str) -> None:
    client = get_storage_client()
    settings = get_settings()
    client.put_object(
        settings.minio_bucket,
        key,
        data,
        length=length,
        content_type=content_type,
    )


async def put_object(*, key: str, data, length: int, content_type: str) -> None:
    await asyncio.to_thread(
        put_object_sync, key=key, data=data, length=length, content_type=content_type
    )


def presigned_get_url(*, key: str, expires_seconds: int = 600) -> str:
    from datetime import timedelta

    client = get_storage_client()
    settings = get_settings()
    return client.presigned_get_object(
        settings.minio_bucket, key, expires=timedelta(seconds=expires_seconds)
    )


def get_object_bytes_sync(key: str) -> bytes:
    client = get_storage_client()
    settings = get_settings()
    response = client.get_object(settings.minio_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def get_object_bytes(key: str) -> bytes:
    return await asyncio.to_thread(get_object_bytes_sync, key)


def object_sha256_sync(key: str) -> tuple[str, int]:
    """流式校验已完成对象，避免把大教材再次读入应用内存。"""
    settings = get_settings()
    response = get_storage_client().get_object(settings.minio_bucket, key)
    digest = hashlib.sha256()
    size = 0
    try:
        for chunk in response.stream(amt=1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    finally:
        response.close()
        response.release_conn()
    return digest.hexdigest(), size


async def object_sha256(key: str) -> tuple[str, int]:
    return await asyncio.to_thread(object_sha256_sync, key)


def copy_object_sync(*, source_key: str, destination_key: str, content_type: str) -> None:
    settings = get_settings()
    get_s3_client().copy_object(
        Bucket=settings.minio_bucket,
        Key=destination_key,
        CopySource={"Bucket": settings.minio_bucket, "Key": source_key},
        ContentType=content_type,
        MetadataDirective="REPLACE",
    )


async def copy_object(*, source_key: str, destination_key: str, content_type: str) -> None:
    await asyncio.to_thread(
        copy_object_sync,
        source_key=source_key,
        destination_key=destination_key,
        content_type=content_type,
    )


def delete_object_sync(key: str) -> None:
    settings = get_settings()
    get_s3_client().delete_object(Bucket=settings.minio_bucket, Key=key)


async def delete_object(key: str) -> None:
    await asyncio.to_thread(delete_object_sync, key)


def create_multipart_upload_sync(*, key: str, content_type: str) -> str:
    settings = get_settings()
    result = get_s3_client().create_multipart_upload(
        Bucket=settings.minio_bucket, Key=key, ContentType=content_type
    )
    return str(result["UploadId"])


async def create_multipart_upload(*, key: str, content_type: str) -> str:
    return await asyncio.to_thread(create_multipart_upload_sync, key=key, content_type=content_type)


def presign_upload_part_sync(*, key: str, upload_id: str, part_number: int) -> str:
    settings = get_settings()
    return get_s3_client().generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.minio_bucket,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=int(timedelta(minutes=20).total_seconds()),
        HttpMethod="PUT",
    )


async def presign_upload_part(*, key: str, upload_id: str, part_number: int) -> str:
    return await asyncio.to_thread(
        presign_upload_part_sync,
        key=key,
        upload_id=upload_id,
        part_number=part_number,
    )


def complete_multipart_upload_sync(*, key: str, upload_id: str, parts: list[dict]) -> None:
    settings = get_settings()
    get_s3_client().complete_multipart_upload(
        Bucket=settings.minio_bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


async def complete_multipart_upload(*, key: str, upload_id: str, parts: list[dict]) -> None:
    await asyncio.to_thread(
        complete_multipart_upload_sync, key=key, upload_id=upload_id, parts=parts
    )


def abort_multipart_upload_sync(*, key: str, upload_id: str) -> None:
    settings = get_settings()
    get_s3_client().abort_multipart_upload(
        Bucket=settings.minio_bucket, Key=key, UploadId=upload_id
    )


async def abort_multipart_upload(*, key: str, upload_id: str) -> None:
    await asyncio.to_thread(abort_multipart_upload_sync, key=key, upload_id=upload_id)
