import logging
from typing import Dict, List, Optional

import click
from aws_orbit.manifest import Manifest
from aws_orbit.messages import print_list, stylize
from aws_orbit.utils import extract_images_names

_logger: logging.Logger = logging.getLogger(__name__)


def _fetch_repo_uri(names: List[str], manifest: Manifest) -> Dict[str, str]:
    names = [f"orbit-{manifest.name}-{x}" for x in names]
    ret: Dict[str, str] = {x: "" for x in names}
    client = manifest.boto3_client("ecr")
    paginator = client.get_paginator("describe_repositories")
    for page in paginator.paginate(repositoryNames=names):
        for repo in page["repositories"]:
            ret[repo["repositoryName"]] = repo["repositoryUri"]
    ret = {k.replace(f"orbit-{manifest.name}-", ""): v for k, v in ret.items()}
    return ret


def list_images(env: str, region: Optional[str]) -> None:
    manifest: Manifest = Manifest(filename=None, env=env, region=region)
    names = extract_images_names(manifest=manifest)
    _logger.debug("names: %s", names)
    if names:
        uris = _fetch_repo_uri(names=names, manifest=manifest)
        print_list(
            tittle=f"Available docker images into the {stylize(manifest.name)} env:",
            items=[f"{k} {stylize(':')} {v}" for k, v in uris.items()],
        )
    else:
        click.echo(f"Thre is no docker images into the {stylize(manifest.name)} env.")