import asyncio
from functools import lru_cache

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
