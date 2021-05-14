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

import base64
import copy
import logging
import re
from typing import Any, Dict, List, Optional, cast

import jsonpatch
import jsonpath_ng
from aws_orbit_admission_controller import load_config
from flask import jsonify
from kubernetes import dynamic
from kubernetes.client import api_client
from kubernetes.dynamic import exceptions as k8s_exceptions

ORBIT_API_VERSION = "v1"
ORBIT_API_GROUP = "orbit.aws"
ORBIT_SYSTEM_NAMESPACE = "orbit-system"
ORBIT_SYSTEM_POD_SETTINGS = None


def get_client() -> dynamic.DynamicClient:
    load_config()
    return dynamic.DynamicClient(client=api_client.ApiClient())


def get_pod_settings(client: dynamic.DynamicClient) -> List[Dict[str, Any]]:
    api = client.resources.get(api_version=ORBIT_API_VERSION, group=ORBIT_API_GROUP, kind="PodSetting")
    pod_settings = api.get()
    return cast(List[Dict[str, Any]], pod_settings.to_dict().get("items", []))


def get_namespace_setting(client: dynamic.DynamicClient, namespace: str, name: str) -> Optional[Dict[str, Any]]:
    api = client.resources.get(api_version=ORBIT_API_VERSION, group=ORBIT_API_GROUP, kind="NamespaceSetting")

    try:
        return cast(Dict[str, Any], api.get(name=name, namespace=namespace).to_dict())
    except k8s_exceptions.NotFoundError:
        return None


def filter_pod_settings(
    pod_settings: List[Dict[str, Any]], namespace: str, pod: Dict[str, Any]
) -> List[Dict[str, Any]]:
    filtered_pod_settings: List[Dict[str, Any]] = []
    for pod_setting in pod_settings:
        if pod_setting["metadata"]["namespace"] != namespace:
            continue

        pod_labels = pod["metadata"].get("labels", {})

        for key, value in pod_setting["spec"]["podSelector"].get("matchLabels", {}).items():
            if pod_labels.get(key, None) != value:
                continue

        for match_expression in pod_setting["spec"]["podSelector"].get("matchExpressions", []):
            pod_label_value = pod_labels.get(match_expression["key"], None)
            operator = match_expression["operator"]
            values = match_expression.get("values", [])

            if operator == "Exists" and pod_label_value is None:
                continue
            if operator == "NotExists" and pod_label_value is not None:
                continue
            if operator == "In" and pod_label_value not in values:
                continue
            if operator == "NotIn" and pod_label_value in values:
                continue

        filtered_pod_settings.append(pod_setting)
    return filtered_pod_settings


def filter_pod_containers(
    containers: List[Dict[str, Any]], pod: Dict[str, Any], container_selector: Dict[str, str]
) -> List[Dict[str, Any]]:
    filtered_containers = []

    if "regex" in container_selector:
        container_selector_regex = (
            re.compile(r".*") if container_selector["regex"] == "*" else re.compile(container_selector["regex"])
        )
        filtered_containers.extend([c for c in containers if container_selector_regex.match(c.get("name", ""))])
    elif "jsonpath" in container_selector:
        container_selector_jsonpath = jsonpath_ng.parse(container_selector["jsonpath"])
        filtered_containers.extend(
            [
                c
                for c in containers
                if c.get("name", "") in [match.value for match in container_selector_jsonpath.find(pod)]
            ]
        )

    return filtered_containers


def apply_settings_to_pod(
    namespace_setting: Dict[str, Any], pod_setting: Dict[str, Any], pod: Dict[str, Any], logger: logging.Logger
) -> None:
    ps_spec = pod_setting["spec"]
    pod_spec = pod["spec"]

    # Merge
    if "serviceAccountName" in ps_spec:
        pod_spec["serviceAccountName"] = ps_spec.get("serviceAccountName", None)

    # Merge
    if "labels" in ps_spec:
        pod["metadata"]["labels"] = {**pod["metadata"].get("labels", {}), **ps_spec.get("labels", {})}

    # Merge
    if "annotations" in ps_spec:
        pod["metadata"]["annotations"] = {**pod["metadata"].get("annotations", {}), **ps_spec.get("annotations", {})}

    # Merge
    if "nodeSelector" in ps_spec:
        pod_spec["nodeSelector"] = {**pod_spec.get("nodeSelector", {}), **ps_spec.get("nodeSelector", {})}

    # Merge
    if "securityContext" in ps_spec:
        pod_spec["securityContext"] = {**pod_spec.get("securityContext", {}), **ps_spec.get("securityContext", {})}

    # Merge
    if "volumes" in ps_spec:
        # Filter out any existing volumes with names that match pod_setting volumes
        pod_spec["volumes"] = [
            pv
            for pv in pod_spec.get("volumes", [])
            if pv["name"] not in [psv["name"] for psv in ps_spec.get("volumes", [])]
        ]
        # Extend pod volumes with pod_setting volumes
        pod_spec["volumes"].extend(ps_spec.get("volumes", []))

    for container in filter_pod_containers(
        containers=pod_spec.get("initContainers", []),
        pod=pod_spec,
        container_selector=ps_spec.get("containerSelector", {}),
    ):
        apply_settings_to_container(namespace_setting=namespace_setting, pod_setting=pod_setting, container=container)
    for container in filter_pod_containers(
        containers=pod_spec.get("containers", []), pod=pod, container_selector=ps_spec.get("containerSelector", {})
    ):
        apply_settings_to_container(namespace_setting=namespace_setting, pod_setting=pod_setting, container=container)
    logger.debug("modified pod: %s", pod)


def apply_settings_to_container(
    namespace_setting: Dict[str, Any], pod_setting: Dict[str, Any], container: Dict[str, Any]
) -> None:
    ns_spec = namespace_setting["spec"]
    ps_spec = pod_setting["spec"]

    if ps_spec.get("injectUserContext", False):
        # Drop any previous USERNAME or USEREMAIL env variables
        ps_spec["env"] = [e for e in ps_spec.get("env", []) if e["name"] not in ["USERNAME", "USEREMAIL"]]
        # Appnend new ones
        ps_spec["env"].extend(
            [{"name": "USERNAME", "value": ns_spec["user"]}, {"name": "USEREMAIL", "value": ns_spec["email"]}]
        )

    # Replace
    if "image" in ps_spec:
        container["image"] = ps_spec.get("image", None)

    # Replace
    if "imagePullPolicy" in ps_spec:
        container["imagePullPolicy"] = ps_spec.get("imagePullPolicy", None)

    # Merge
    if "lifecycle" in ps_spec:
        container["lifecycle"] = {**container.get("lifecycle", {}), **ps_spec.get("lifecycle", {})}

    # Replace
    if "command" in ps_spec:
        container["command"] = ps_spec["command"]

    # Replace
    if "args" in ps_spec:
        container["args"] = ps_spec["args"]

    # Merge
    if "env" in ps_spec:
        # Filter out any existing env items with names that match pod_setting env items
        container["env"] = [
            pv for pv in container.get("env", []) if pv["name"] not in [psv["name"] for psv in ps_spec.get("env", [])]
        ]
        # Extend container env items with container pod_setting env items
        container["env"].extend(ps_spec.get("env", []))

    # Extend
    if "envFrom" in ps_spec:
        # Extend container envFrom with pod_setting envFrom
        container["envFrom"].extend(ps_spec.get("envFrom", []))

    # Merge
    if "volumeMounts" in ps_spec:
        # Filter out any existing volumes with names that match pod_setting volumes
        container["volumeMounts"] = [
            pv
            for pv in container.get("volumeMounts", [])
            if pv["name"] not in [psv["name"] for psv in ps_spec.get("volumeMounts", [])]
        ]
        # Extend container volumes with container volumes
        container["volumeMounts"].extend(ps_spec.get("volumeMounts", []))


def get_response(uid: str, patch: Optional[Dict[str, Any]] = None) -> str:
    if patch:
        return cast(
            str,
            jsonify(
                {
                    "response": {
                        "allowed": True,
                        "uid": uid,
                        "patch": base64.b64encode(str(patch).encode()).decode(),
                        "patchtype": "JSONPatch",
                    }
                }
            ),
        )
    else:
        return cast(
            str,
            jsonify(
                {
                    "response": {
                        "allowed": True,
                        "uid": uid,
                    }
                }
            ),
        )


def process_request(logger: logging.Logger, request: Dict[str, Any]) -> Any:
    if request.get("dryRun", False):
        logger.info("Dry run - Skip Pod Mutation")
        return get_response(uid=request["uid"])

    pod = request["object"]
    modified_pod = copy.deepcopy(pod)

    logger.info("request: %s", request)

    client = get_client()
    global ORBIT_SYSTEM_POD_SETTINGS
    ORBIT_SYSTEM_POD_SETTINGS = (
        get_pod_settings(client=client) if ORBIT_SYSTEM_POD_SETTINGS is None else ORBIT_SYSTEM_POD_SETTINGS
    )
    logger.debug("podsettings: %s", ORBIT_SYSTEM_POD_SETTINGS)

    namespace_setting = get_namespace_setting(
        client=client, namespace=ORBIT_SYSTEM_NAMESPACE, name=request["namespace"]
    )
    if namespace_setting is None:
        logger.info("namespacesetting named %s not found in namesapce %s", request["namespace"], ORBIT_SYSTEM_NAMESPACE)
        return get_response(uid=request["uid"])

    team_namespace = namespace_setting["spec"]["team"]
    team_pod_settings = filter_pod_settings(pod_settings=ORBIT_SYSTEM_POD_SETTINGS, namespace=team_namespace, pod=pod)
    logger.debug("filtered podsettings: %s", team_pod_settings)

    try:
        for pod_setting in team_pod_settings:
            logger.debug("applying podsetting: %s", pod_setting)
            apply_settings_to_pod(
                namespace_setting=namespace_setting, pod_setting=pod_setting, pod=modified_pod, logger=logger
            )
    except Exception as e:
        logger.exception(e)
        pass

    patch = jsonpatch.JsonPatch.from_diff(pod, modified_pod)
    logger.info("patch: %s", str(patch).encode())
    return get_response(uid=request["uid"], patch=patch)
