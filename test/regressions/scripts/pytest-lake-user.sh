#!/bin/bash

set -e

# Required os env variables. Replace with testing Orbit env details
# AWS_ORBIT_ENV, AWS_ORBIT_TEAM_SPACE

# Set the .kube/config with respect to runtime environment
pytest --kube-config ~/.kube/config -v -s  -k testlakeuser -n auto