import sys
from pathlib import Path

import pytest

from checkov.kubernetes.parser.parser import GENERATED_NAME_INDEX, _set_generated_name_indices, parse


@pytest.mark.parametrize("container_type", [dict, list], ids=["dictionaries", "lists"])
def test_indexing_handles_nesting_beyond_python_recursion_limit(container_type: type) -> None:
    deepest_resource = {"metadata": {"generateName": "deep-"}}
    nested = deepest_resource
    for _ in range(sys.getrecursionlimit() + 100):
        nested = {"nested": nested} if container_type is dict else [nested]
    sibling = {"metadata": {"generateName": "sibling-"}}

    next_index = _set_generated_name_indices([nested, sibling], next_index=7)

    assert deepest_resource[GENERATED_NAME_INDEX] == 7
    assert sibling[GENERATED_NAME_INDEX] == 8
    assert next_index == 9


def test_parser_indexes_resources_after_a_cyclic_yaml_list(tmp_path: Path) -> None:
    manifest = tmp_path / "cycle.yaml"
    manifest.write_text(
        "apiVersion: example.com/v1\nkind: Example\n"
        "metadata:\n  generateName: first-\n"
        "spec:\n  values: &cycle [*cycle]\n"
        "---\napiVersion: example.com/v1\nkind: Example\n"
        "metadata:\n  generateName: second-\n"
    )

    definitions, _ = parse(str(manifest))

    assert definitions[0]["spec"]["values"][0] is definitions[0]["spec"]["values"]
    assert [resource[GENERATED_NAME_INDEX] for resource in definitions] == [1, 2]


def test_parser_indexes_shared_yaml_mappings_once(tmp_path: Path) -> None:
    manifest = tmp_path / "aliases.yaml"
    manifest.write_text(
        "apiVersion: example.com/v1\nkind: Example\n"
        "metadata:\n  generateName: parent-\n"
        "spec:\n"
        "  shared: &shared\n    metadata:\n      generateName: shared-\n"
        "  copies: [*shared, *shared]\n"
        "  last:\n    metadata:\n      generateName: last-\n"
    )

    definitions, _ = parse(str(manifest))

    parent = definitions[0]
    shared = parent["spec"]["shared"]
    assert all(copy is shared for copy in parent["spec"]["copies"])
    assert parent[GENERATED_NAME_INDEX] == 1
    assert shared[GENERATED_NAME_INDEX] == 2
    assert parent["spec"]["last"][GENERATED_NAME_INDEX] == 3
