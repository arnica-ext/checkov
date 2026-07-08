#!/bin/bash
set -e

# Arnica checkov fork release helper, mirroring the arnica-ext/trivy `tag.sh` convention:
#   branch: <upstream-version>-arnica-patch
#   tag:    <upstream-version>-arnica-patch-0.0.N
# Bump TAG for each new patch release, then run this script from the repo root.
TAG="3.2.404-arnica-patch-0.0.1"

# `checkov/version.py` must be a PEP 440 valid string (setuptools rejects the dashed tag form),
# so the patch identifier is encoded as a PEP 440 local-version segment.
# e.g. 3.2.404-arnica-patch-0.0.1 -> 3.2.404+arnica.patch.0.0.1
VERSION="${TAG/-arnica-patch-/+arnica.patch.}"

sed -i '' -E "s/^version = .*/version = '$VERSION'/" checkov/version.py

if ! git diff --quiet checkov/version.py; then
  git add checkov/version.py
  git commit -m "Update tag to $TAG"
else
  echo "checkov/version.py is up-to-date"
fi

git push origin HEAD
git tag "$TAG"
git push origin "$TAG"
