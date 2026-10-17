#!/usr/bin/env bash
set -euo pipefail

base_revision="${1:?base commit required}"
head_revision="${2:?head commit required}"
git rev-parse --verify "${head_revision}^{commit}" > /dev/null

if [[ "$base_revision" == 0000000000000000000000000000000000000000 ]]; then
    # A new main branch has no previous commit: check all committed content.
    empty_tree=$(git hash-object -t tree -w /dev/null)
    git diff --check "$empty_tree" "$head_revision" --
else
    git rev-parse --verify "${base_revision}^{commit}" > /dev/null
    git diff --check "$base_revision...$head_revision" --
fi
