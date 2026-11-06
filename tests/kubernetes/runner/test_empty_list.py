from pathlib import Path

import pytest

from checkov.kubernetes.kubernetes_utils import build_definitions_context, create_definitions
from checkov.kubernetes.runner import Runner
from checkov.runner_filter import RunnerFilter
from tests.graph_utils.utils import GRAPH_FRAMEWORKS


@pytest.fixture(params=["items: null", "items: []", ""], ids=["null", "empty", "missing"])
def list_manifest(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    manifest = tmp_path / "list.yaml"
    manifest.write_text(
        f"apiVersion: v1\nkind: List\n{request.param}\n"
        "---\n"
        "apiVersion: v1\n"
        "kind: List\n"
        "items:\n"
        "  - null\n"
        "  - apiVersion: v1\n"
        "    kind: ConfigMap\n"
        "    metadata:\n"
        "      name: listed\n"
        "      namespace: app\n"
        "    data:\n"
        "      key: value\n"
        "---\n"
        "apiVersion: v1\n"
        "kind: ConfigMap\n"
        "metadata:\n"
        "  name: standalone\n"
        "  namespace: app\n"
        "data:\n"
        "  key: value\n"
    )
    return manifest


def test_context_ignores_empty_list_and_preserves_other_resources(list_manifest: Path) -> None:
    definitions, definitions_raw = create_definitions(root_folder=None, files=[str(list_manifest)])

    context = build_definitions_context(definitions, definitions_raw)

    assert set(context[str(list_manifest)]) == {"ConfigMap.app.listed", "ConfigMap.app.standalone"}


@pytest.mark.parametrize("graph_framework", GRAPH_FRAMEWORKS)
def test_runner_scans_other_resources_beside_empty_list(
    list_manifest: Path, graph_framework: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHECKOV_GRAPH_FRAMEWORK", graph_framework)
    runner = Runner()

    report = runner.run(
        root_folder=None,
        files=[str(list_manifest)],
        runner_filter=RunnerFilter(checks=["CKV_K8S_21"]),
    )

    assert len(report.passed_checks) == 2
    assert not report.failed_checks
    assert not report.parsing_errors
    assert {resource["metadata"]["name"] for resource in runner.definitions[str(list_manifest)]} == {
        "listed", "standalone"
    }
