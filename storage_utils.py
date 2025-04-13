from minio import Minio

client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

def upload_to_minio(file_path: str, bucket: str, object_name: str):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.fput_object(bucket, object_name, file_path)
    return f"http://localhost:9000/{bucket}/{object_name}"

def delete_from_minio(bucket: str, object_name: str):
    client.remove_object(bucket, object_name)
