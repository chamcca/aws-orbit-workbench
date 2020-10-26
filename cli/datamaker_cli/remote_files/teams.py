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

import logging

from datamaker_cli import plugins
from datamaker_cli.manifest import Manifest
from datamaker_cli.remote_files import cdk
from datamaker_cli.services import cfn, s3

_logger: logging.Logger = logging.getLogger(__name__)


def deploy(manifest: Manifest) -> None:
    for team_manifest in manifest.teams:
        template_filename = cdk.team.synth(
            manifest=manifest,
            team_manifest=team_manifest,
        )
        _logger.debug("template_filename: %s", template_filename)
        cfn.deploy_template(
            manifest=manifest,
            stack_name=team_manifest.stack_name,
            filename=template_filename,
            env_tag=manifest.env_tag,
        )
        team_manifest.fetch_ssm()
        for plugin in plugins.PLUGINS_REGISTRY.values():
            if plugin.deploy_team_hook is not None:
                plugin.deploy_team_hook(manifest, team_manifest)


def destroy(manifest: Manifest) -> None:
    for team_manifest in manifest.teams:
        for plugin in plugins.PLUGINS_REGISTRY.values():
            if plugin.destroy_team_hook is not None:
                plugin.destroy_team_hook(manifest, team_manifest)
        _logger.debug("Stack name: %s", team_manifest.stack_name)
        if cfn.does_stack_exist(manifest=manifest, stack_name=manifest.toolkit_stack_name):
            if team_manifest.scratch_bucket is not None:
                s3.delete_bucket(manifest=manifest, bucket=team_manifest.scratch_bucket)
            cfn.destroy_stack(manifest=manifest, stack_name=team_manifest.stack_name)