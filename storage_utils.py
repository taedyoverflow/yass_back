from minio import Minio
import mimetypes

# MinIO 클라이언트: 내부통신은 그대로 유지 (localhost)
client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False  # 내부 통신이니까 HTTPS 필요 없음
)

def upload_to_minio(file_path: str, bucket: str, object_name: str):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"  # fallback

    client.fput_object(
        bucket_name=bucket,
        object_name=object_name,
        file_path=file_path,
        content_type=content_type  # ✅ 여기에 명시!
    )

    return f"https://yass-ai.com/minio/{bucket}/{object_name}"

def delete_from_minio(bucket: str, object_name: str):
    client.remove_object(bucket, object_name)
