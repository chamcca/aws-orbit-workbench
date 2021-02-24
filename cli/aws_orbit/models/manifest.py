#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License").
#    You may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# flake8: noqa: F811

import json
import logging
import os
import re
from typing import Any, ClassVar, Dict, List, Optional, Type, Union, cast

import jsonpath_ng as jsonpath_ng
import yaml
from dataclasses import field
from marshmallow import Schema
from marshmallow_dataclass import dataclass
from yamlinclude import YamlIncludeConstructor

from aws_orbit import utils
from aws_orbit.models.common import BaseSchema
from aws_orbit.services import ssm
from aws_orbit.utils import boto3_client

_logger: logging.Logger = logging.getLogger(__name__)

SSM_CONTEXT: Dict[str, str] = {}


@dataclass(base_schema=BaseSchema, frozen=True)
class PluginManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    plugin_id: str
    module: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    path: Optional[str] = None


@dataclass(base_schema=BaseSchema, frozen=True)
class TeamManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    name: str
    policies: List[str] = field(default_factory=list)
    grant_sudo: bool = False
    jupyterhub_inbound_ranges: List[str] = field(default_factory=lambda: ["0.0.0.0/0"])
    image: Optional[str] = None
    plugins: List[PluginManifest] = field(default_factory=list)
    profiles: List[Dict[str, Union[str, Dict[str, Any]]]] = field(default_factory=list)
    efs_life_cycle: Optional[str] = None


@dataclass(base_schema=BaseSchema, frozen=True)
class ImageManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    repository: str
    source: str = "dockerhub"
    version: str = "latest"
    path: Optional[str] = None


@dataclass(base_schema=BaseSchema, frozen=True)
class ManagedNodeGroupManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    name: str
    instance_type: str = "m5.4xlarge"
    local_storage_size: int = 128
    nodes_num_desired: int = 2
    nodes_num_max: int = 3
    nodes_num_min: int = 1
    labels: Dict[str, str] = field(default_factory=dict)
    enable_virtual_gpu: bool = False


@dataclass(base_schema=BaseSchema, frozen=True)
class CodeBuildImageManifest(ImageManifest):
    repository: str = "aws-orbit-code-build-base"


@dataclass(base_schema=BaseSchema, frozen=True)
class JupyterHubImageManifest(ImageManifest):
    repository: str = "aws-orbit-jupyter-hub"


@dataclass(base_schema=BaseSchema, frozen=True)
class JupyterUserImageManifest(ImageManifest):
    repository: str = "aws-orbit-jupyter-user"


@dataclass(base_schema=BaseSchema, frozen=True)
class JupyterUserSparkImageManifest(ImageManifest):
    repository: str = "aws-orbit-jupyter-user-spark"


@dataclass(base_schema=BaseSchema, frozen=True)
class GpuJupyterUserImageManifest(ImageManifest):
    repository: str = "aws-orbit-gpu-jupyter-user"


@dataclass(base_schema=BaseSchema, frozen=True)
class LandingPageImageManifest(ImageManifest):
    repository: str = "aws-orbit-landing-page"


@dataclass(base_schema=BaseSchema, frozen=True)
class AwsEfsDriverImageManifest(ImageManifest):
    repository: str = "602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/aws-efs-csi-driver"
    source: str = "ecr-external"
    version: str = "v1.0.0"


@dataclass(base_schema=BaseSchema, frozen=True)
class LivenessprobeImageManifest(ImageManifest):
    repository: str = "602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/livenessprobe"
    source: str = "ecr-external"
    version: str = "v2.0.0"


@dataclass(base_schema=BaseSchema, frozen=True)
class CsiNodeDriverRegistrarImageManifest(ImageManifest):
    repository: str = "602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/csi-node-driver-registrar"
    source: str = "ecr-external"
    version: str = "v1.3.0"


@dataclass(base_schema=BaseSchema, frozen=True)
class ImagesManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    code_build: CodeBuildImageManifest = CodeBuildImageManifest()
    jupyter_hub: JupyterHubImageManifest = JupyterHubImageManifest()
    jupyter_user: JupyterUserImageManifest = JupyterUserImageManifest()
    jupyter_user_spark: JupyterUserSparkImageManifest = JupyterUserSparkImageManifest()
    gpu_jupyter_user: GpuJupyterUserImageManifest = GpuJupyterUserImageManifest()
    landing_page: LandingPageImageManifest = LandingPageImageManifest()
    aws_efs_csi_driver: AwsEfsDriverImageManifest = AwsEfsDriverImageManifest()
    livenessprobe: LivenessprobeImageManifest = LivenessprobeImageManifest()
    csi_node_driver_registrar: CsiNodeDriverRegistrarImageManifest = CsiNodeDriverRegistrarImageManifest()
    names: List[str] = field(
        metadata=dict(load_only=True),
        default_factory=lambda: [
            "code_build",
            "jupyter_hub",
            "jupyter_user",
            "jupyter_user_spark",
            "gpu_jupyter_user",
            "landing_page",
            "aws_efs_csi_driver",
            "livenessprobe",
            "csi_node_driver_registrar",
        ],
    )


@dataclass(base_schema=BaseSchema, frozen=True)
class FrontendNetworkingManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    load_balancers_subnets: List[str] = field(default_factory=list)


@dataclass(base_schema=BaseSchema, frozen=True)
class DataNetworkingManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    internet_accessible: bool = False
    nodes_subnets: List[str] = field(default_factory=list)


@dataclass(base_schema=BaseSchema, frozen=True)
class NetworkingManifest:
    Schema: ClassVar[Type[Schema]] = Schema
    vpc_id: Optional[str] = None
    public_subnets: List[str] = field(default_factory=list)
    private_subnets: List[str] = field(default_factory=list)
    isolated_subnets: List[str] = field(default_factory=list)
    frontend: FrontendNetworkingManifest = FrontendNetworkingManifest()
    data: DataNetworkingManifest = DataNetworkingManifest()


@dataclass(base_schema=BaseSchema, frozen=True)
class Manifest:
    Schema: ClassVar[Type[Schema]] = Schema
    name: str
    user_pool_id: Optional[str] = None
    scratch_bucket_arn: Optional[str] = None
    eks_system_masters_roles: List[str] = field(default_factory=list)
    codeartifact_domain: Optional[str] = None
    codeartifact_repository: Optional[str] = None
    cognito_external_provider: Optional[str] = None
    cognito_external_provider_label: Optional[str] = None
    networking: NetworkingManifest = NetworkingManifest()
    teams: List[TeamManifest] = field(default_factory=list)
    images: ImagesManifest = ImagesManifest()
    shared_efs_fs_id: Optional[str] = None
    shared_efs_sg_id: Optional[str] = None
    managed_nodegroups: List[ManagedNodeGroupManifest] = field(default_factory=list)

    def get_team_by_name(self, name: str) -> Optional[TeamManifest]:
        for t in self.teams:
            if t.name == name:
                return t
        return None


def _add_ssm_param_injector(tag: str = "!SSM") -> None:
    """
    Load a yaml configuration file and resolve any SSM parameters
    The SSM parameters must have !SSM before them and be in this format
    to be parsed: ${SSM_PARAMETER_PATH::JSONPATH}.
    E.g.:
    database:
        host: !SSM ${/orbit/dev-env/demo::/UserAccessPolicy}
        port: !SSM ${/orbit/dev-env/demo::/PublicSubnet/*}
    """
    # pattern for global vars: look for ${word}
    pattern = re.compile(".*?\${(.*)}.*?")  # noqa: W605
    loader = yaml.SafeLoader

    # the tag will be used to mark where to start searching for the pattern
    # e.g. somekey: !SSM somestring${MYENVVAR}blah blah blah
    loader.add_implicit_resolver(tag, pattern, None)  # type: ignore

    def constructor_ssm_parameter(loader, node) -> Any:  # type: ignore
        """
        Extracts the environment variable from the node's value
        :param yaml.Loader loader: the yaml loader
        :param node: the current node in the yaml
        :return: the parsed string that contains the value of the environment
        variable
        """
        value = loader.construct_scalar(node)
        match = pattern.findall(value)  # to find all env variables in line
        if match:
            full_value = value
            for g in match:
                _logger.debug(f"match: {g}")
                (ssm_param_name, jsonpath) = g.split("::")
                _logger.debug(f"found injected parameter {(ssm_param_name, jsonpath)}")
                if ssm_param_name not in SSM_CONTEXT:
                    ssm = boto3_client("ssm")
                    try:
                        SSM_CONTEXT[ssm_param_name] = json.loads(
                            ssm.get_parameter(Name=ssm_param_name)["Parameter"]["Value"]
                        )
                    except Exception as e:
                        _logger.error(f"Error resolving injected parameter {g}: {e}")
                        pass

                json_expr = jsonpath_ng.parse(jsonpath)
                json_data = SSM_CONTEXT[ssm_param_name]
                json_match = json_expr.find(json_data)

                if len(json_match) > 1:
                    raise Exception(f"Injected parameter {g} is ambiguous")
                elif len(json_match) == 0:
                    raise Exception(f"Injected parameter {jsonpath} not found in SSM {ssm_param_name}")

                param_value: str = json_match[0].value
                _logger.debug(f"injected SSM parameter {g} resolved to {param_value}")
                return param_value
            return full_value
        return value

    loader.add_constructor(tag, constructor_ssm_parameter)  # type: ignore


def _add_env_var_injector(tag: str = "!ENV") -> None:
    """
    Load a yaml configuration file and resolve any environment variables
    The environment variables must have !ENV before them and be in this format
    to be parsed: ${VAR_NAME}.
    E.g.:
    database:
        host: !ENV ${HOST}
        port: !ENV ${PORT}
    app:
        log_path: !ENV '/var/${LOG_PATH}'
        something_else: !ENV '${AWESOME_ENV_VAR}/var/${A_SECOND_AWESOME_VAR}'
    """
    # pattern for global vars: look for ${word}
    pattern = re.compile(".*?\${(.*)}.*?")  # noqa: W605
    loader = yaml.SafeLoader

    # the tag will be used to mark where to start searching for the pattern
    # e.g. somekey: !ENV somestring${MYENVVAR}blah blah blah
    loader.add_implicit_resolver(tag, pattern, None)  # type: ignore

    def constructor_env_variables(loader, node) -> Any:  # type: ignore
        """
        Extracts the environment variable from the node's value
        :param yaml.Loader loader: the yaml loader
        :param node: the current node in the yaml
        :return: the parsed string that contains the value of the environment
        variable
        """
        value = loader.construct_scalar(node)
        match = pattern.findall(value)  # to find all env variables in line
        if match:
            full_value = value
            for g in match:
                (env_var, default_val) = g.split("::")
                value = os.environ.get(env_var, default_val)
                full_value = full_value.replace(f"${{{g}}}", value)
                _logger.debug(f"injected ENV parameter {env_var} resolved to {value}")
            return full_value
        return value

    loader.add_constructor(tag, constructor_env_variables)  # type: ignore


def load_manifest_from_file(filename: str) -> Manifest:
    _logger.debug("Loading manifest file (%s)", filename)
    filepath = os.path.abspath(filename)
    _logger.debug("filepath: %s", filepath)
    filedir: str = os.path.dirname(filepath)
    utils.print_dir(dir=filedir)
    YamlIncludeConstructor.add_to_loader_class(loader_class=yaml.SafeLoader, base_dir=filedir)
    _add_ssm_param_injector()
    _add_env_var_injector()
    with open(filepath, "r") as f:
        raw: Dict[str, Any] = cast(Dict[str, Any], yaml.safe_load(f))
    _logger.debug("raw: %s", raw)
    manifest: Manifest = cast(Manifest, Manifest.Schema().load(data=raw, many=False, partial=False, unknown="RAISE"))
    dump_manifest_to_ssm(manifest=manifest)
    return manifest


def dump_manifest_to_file(manifest: Manifest, filepath: str) -> None:
    _logger.debug("Dumping manifest file (%s)", filepath)
    content: Dict[str, Any] = cast(Dict[str, Any], Manifest.Schema().dump(manifest))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        yaml.dump(content, f, sort_keys=False)


def dump_manifest_to_ssm(manifest: Manifest) -> None:
    _logger.debug("Writing manifest to SSM parameter.")
    _logger.debug("Teams: %s", [t.name for t in manifest.teams])
    content: Dict[str, Any] = cast(Dict[str, Any], Manifest.Schema().dump(manifest))
    ssm.cleanup_manifest(env_name=manifest.name)
    if "Teams" in content:
        for team in content["Teams"]:
            team_parameter_name: str = f"/orbit/{manifest.name}/teams/{team['Name']}/manifest"
            ssm.put_parameter(name=team_parameter_name, obj=team)
        del content["Teams"]
    manifest_parameter_name: str = f"/orbit/{manifest.name}/manifest"
    ssm.put_parameter(name=manifest_parameter_name, obj=content)


def load_manifest_from_ssm(env_name: str) -> Optional[Manifest]:
    context_parameter_name: str = f"/orbit/{env_name}/manifest"
    main = ssm.get_parameter_if_exists(name=context_parameter_name)
    if main is None:
        return None
    teams_parameters = ssm.list_parameters(prefix=f"/orbit/{env_name}/teams/")
    _logger.debug("teams_parameters: %s", teams_parameters)
    teams = [ssm.get_parameter(name=p) for p in teams_parameters if p.endswith("/manifest")]
    main["Teams"] = teams
    return cast(Manifest, Manifest.Schema().load(data=main, many=False, partial=False, unknown="RAISE"))
