import logging
import os
from typing import List

from datamaker_cli import DATAMAKER_CLI_ROOT, sh
from datamaker_cli.manifest import Manifest

_logger: logging.Logger = logging.getLogger(__name__)


def _get_app_argument(app_filename: str, args: List[str]) -> str:
    path: str = os.path.join(DATAMAKER_CLI_ROOT, "remote_files", "cdk", app_filename)
    args_str: str = " ".join(args)
    return f'--app "python {path} {args_str}"'


def _get_output_argument(manifest: Manifest, stack_name: str) -> str:
    path: str = os.path.join(manifest.filename_dir, ".datamaker.out", manifest.name, "cdk", stack_name)
    return f"--output {path}"


def deploy(manifest: Manifest, stack_name: str, app_filename: str, args: List[str]) -> None:
    if manifest.cdk_toolkit_stack_name is None:
        raise ValueError(f"manifest.cdk_toolkit_stack_name: {manifest.cdk_toolkit_stack_name}")
    cmd: str = (
        "cdk deploy --require-approval never --progress events "
        f"--toolkit-stack-name {manifest.cdk_toolkit_stack_name} "
        f"{_get_app_argument(app_filename, args)} "
        f"{_get_output_argument(manifest, stack_name)}"
    )
    sh.run(cmd=cmd)


def destroy(manifest: Manifest, stack_name: str, app_filename: str, args: List[str]) -> None:
    if manifest.cdk_toolkit_stack_name is None:
        raise ValueError(f"manifest.cdk_toolkit_stack_name: {manifest.cdk_toolkit_stack_name}")
    cmd: str = (
        "cdk destroy --force "
        f"--toolkit-stack-name {manifest.cdk_toolkit_stack_name} "
        f"{_get_app_argument(app_filename, args)} "
        f"{_get_output_argument(manifest, stack_name)}"
    )
    sh.run(cmd=cmd)


def deploy_toolkit(manifest: Manifest) -> None:
    if manifest.cdk_toolkit_stack_name is None:
        raise ValueError(f"manifest.cdk_toolkit_stack_name: {manifest.cdk_toolkit_stack_name}")
    cmd: str = (
        f"cdk bootstrap --toolkit-bucket-name {manifest.cdk_toolkit_s3_bucket} "
        f"--toolkit-stack-name {manifest.cdk_toolkit_stack_name} "
        f"{_get_output_argument(manifest, manifest.cdk_toolkit_stack_name)} "
        f"aws://{manifest.account_id}/{manifest.region}"
    )
    sh.run(cmd=cmd)