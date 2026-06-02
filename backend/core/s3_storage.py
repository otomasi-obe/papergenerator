"""
S3-Compatible Storage Module
=============================
Provides S3 storage operations for file uploads using boto3.
Supports AWS S3, MinIO, DigitalOcean Spaces, and other S3-compatible providers.

Configuration via environment variables:
- S3_ENABLED: 'true' to use S3, 'false' for local filesystem
- S3_ENDPOINT_URL: S3 endpoint (e.g., http://localhost:9000 for MinIO)
- S3_ACCESS_KEY_ID: Access key
- S3_SECRET_ACCESS_KEY: Secret key
- S3_BUCKET_NAME: Bucket name
- S3_REGION: Region (e.g., us-east-1)
"""

import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

# S3 Configuration from environment
S3_ENABLED = os.getenv("S3_ENABLED", "false").lower() == "true"
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "papergenerator-files")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

# Lazy-initialized S3 client
_s3_client = None


def _get_s3_client():
    """Get or create S3 client singleton."""
    global _s3_client
    if _s3_client is None:
        try:
            # Configure boto3 client
            config = Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},  # Required for MinIO
            )

            _s3_client = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                region_name=S3_REGION,
                config=config,
            )

            # Test connection and create bucket if it doesn't exist
            try:
                _s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
                log.info("Connected to S3 bucket: %s", S3_BUCKET_NAME)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code == "404":
                    # Bucket doesn't exist, create it
                    log.info("Creating S3 bucket: %s", S3_BUCKET_NAME)
                    if S3_REGION == "us-east-1":
                        _s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                    else:
                        _s3_client.create_bucket(
                            Bucket=S3_BUCKET_NAME,
                            CreateBucketConfiguration={"LocationConstraint": S3_REGION},
                        )
                else:
                    raise
        except Exception as e:
            log.error("Failed to initialize S3 client: %s", e)
            raise

    return _s3_client


def is_s3_enabled() -> bool:
    """Check if S3 storage is enabled."""
    return S3_ENABLED


def upload_file(file_data: bytes, s3_key: str, content_type: str = "application/octet-stream") -> bool:
    """
    Upload file to S3.

    Args:
        file_data: File content as bytes
        s3_key: S3 object key (path in bucket)
        content_type: MIME type of the file

    Returns:
        bool: True if successful, False otherwise
    """
    if not S3_ENABLED:
        log.warning("S3 is disabled, cannot upload file: %s", s3_key)
        return False

    try:
        client = _get_s3_client()
        client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_data,
            ContentType=content_type,
        )
        log.info("Uploaded file to S3: %s", s3_key)
        return True
    except Exception as e:
        log.error("Failed to upload file to S3 (%s): %s", s3_key, e)
        return False


def download_file(s3_key: str) -> Optional[bytes]:
    """
    Download file from S3.

    Args:
        s3_key: S3 object key (path in bucket)

    Returns:
        bytes: File content, or None if failed
    """
    if not S3_ENABLED:
        log.warning("S3 is disabled, cannot download file: %s", s3_key)
        return None

    try:
        client = _get_s3_client()
        response = client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        data = response["Body"].read()
        log.info("Downloaded file from S3: %s (%d bytes)", s3_key, len(data))
        return data
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "NoSuchKey":
            log.warning("File not found in S3: %s", s3_key)
        else:
            log.error("Failed to download file from S3 (%s): %s", s3_key, e)
        return None
    except Exception as e:
        log.error("Failed to download file from S3 (%s): %s", s3_key, e)
        return None


def download_file_to_path(s3_key: str, local_path: Path) -> bool:
    """
    Download file from S3 to local path.

    Args:
        s3_key: S3 object key (path in bucket)
        local_path: Local file path to save to

    Returns:
        bool: True if successful, False otherwise
    """
    data = download_file(s3_key)
    if data is None:
        return False

    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return True
    except Exception as e:
        log.error("Failed to write downloaded file to %s: %s", local_path, e)
        return False


def delete_file(s3_key: str) -> bool:
    """
    Delete file from S3.

    Args:
        s3_key: S3 object key (path in bucket)

    Returns:
        bool: True if successful, False otherwise
    """
    if not S3_ENABLED:
        log.warning("S3 is disabled, cannot delete file: %s", s3_key)
        return False

    try:
        client = _get_s3_client()
        client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        log.info("Deleted file from S3: %s", s3_key)
        return True
    except Exception as e:
        log.error("Failed to delete file from S3 (%s): %s", s3_key, e)
        return False


def generate_presigned_url(s3_key: str, expiration: int = 3600) -> Optional[str]:
    """
    Generate presigned URL for temporary file access.

    Args:
        s3_key: S3 object key (path in bucket)
        expiration: URL expiration time in seconds (default: 1 hour)

    Returns:
        str: Presigned URL, or None if failed
    """
    if not S3_ENABLED:
        log.warning("S3 is disabled, cannot generate presigned URL: %s", s3_key)
        return None

    try:
        client = _get_s3_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiration,
        )
        log.info("Generated presigned URL for S3 key: %s", s3_key)
        return url
    except Exception as e:
        log.error("Failed to generate presigned URL for %s: %s", s3_key, e)
        return None


def file_exists(s3_key: str) -> bool:
    """
    Check if file exists in S3.

    Args:
        s3_key: S3 object key (path in bucket)

    Returns:
        bool: True if file exists, False otherwise
    """
    if not S3_ENABLED:
        return False

    try:
        client = _get_s3_client()
        client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return True
    except ClientError:
        return False
    except Exception as e:
        log.error("Failed to check file existence in S3 (%s): %s", s3_key, e)
        return False
