from minio import Minio

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
    client.fput_object(bucket, object_name, file_path)

    # ✅ 브라우저 접근용 URL은 HTTPS + 도메인 + /minio 접두어 사용
    return f"https://yass-ai.com/minio/{bucket}/{object_name}"

def delete_from_minio(bucket: str, object_name: str):
    client.remove_object(bucket, object_name)
