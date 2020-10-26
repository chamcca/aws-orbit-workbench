import json
from typing import TYPE_CHECKING, Dict, Tuple

import botocore

from datamaker_cli.services import s3

if TYPE_CHECKING:
    from datamaker_cli.manifest import Manifest


def get_credential(manifest: "Manifest") -> Tuple[str, str]:
    client_s3 = manifest.boto3_client(service_name="s3")
    obj = client_s3.get_object(Bucket=manifest.toolkit_s3_bucket, Key="cli/dockerhub.json")
    obj_json: Dict[str, str] = json.loads(obj["Body"].read())
    return obj_json["username"], obj_json["password"]


def store_credential(manifest: "Manifest", username: str, password: str) -> None:
    if manifest.toolkit_s3_bucket is None:
        raise ValueError(f"manifest.toolkit_s3_bucket: {manifest.toolkit_s3_bucket}")
    s3.delete_objects(
        manifest=manifest,
        bucket=manifest.toolkit_s3_bucket,
        keys=["cli/dockerhub.json"],
    )
    client_s3 = manifest.boto3_client(service_name="s3")
    client_s3.put_object(
        Body=json.dumps({"username": username, "password": password}).encode("utf-8"),
        Bucket=manifest.toolkit_s3_bucket,
        Key="cli/dockerhub.json",
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=manifest.toolkit_kms_arn,
    )


def does_credential_exist(manifest: "Manifest") -> bool:
    client_s3 = manifest.boto3_client(service_name="s3")
    try:
        client_s3.head_object(Bucket=manifest.toolkit_s3_bucket, Key="cli/dockerhub.json")
        return True
    except botocore.exceptions.ClientError as ex:
        if ex.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise ex