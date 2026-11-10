from copy import deepcopy
import json
from pathlib import Path

import pytest

from checkov.kubernetes.graph_builder.local_graph import KubernetesLocalGraph
from checkov.kubernetes.kubernetes_utils import (
    PARENT_RESOURCE_ID_KEY_NAME,
    build_definitions_context,
    create_definitions,
    get_resource_id,
)
from checkov.kubernetes.runner import Runner
from checkov.kubernetes.parser.parser import GENERATED_NAME_INDEX
from checkov.runner_filter import RunnerFilter
from tests.graph_utils.utils import GRAPH_FRAMEWORKS


@pytest.fixture(params=["Job", "Deployment", "Pod"])
def generated_manifest(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    path = tmp_path / "generated.yaml"
    pod_spec = "    containers:\n      - name: example\n        image: busybox:1.36\n    restartPolicy: Never\n"
    if request.param == "Pod":
        # Standalone Pods must also be accepted without names or labels.
        spec = "spec:\n" + "\n".join(line[2:] for line in pod_spec.splitlines()) + "\n"
    else:
        spec = (
            "spec:\n  template:\n    metadata:\n      labels:\n        app: example\n    spec:\n"
            + "".join("  " + line + "\n" for line in pod_spec.splitlines())
        )
    path.write_text("---\n".join(
        f"apiVersion: {'v1' if request.param == 'Pod' else 'batch/v1' if request.param == 'Job' else 'apps/v1'}\n"
        f"kind: {request.param}\nmetadata:\n  generateName: {prefix}\n  namespace: app\n" + spec
        for prefix in ("first-", "second-")
    ))
    return path


@pytest.mark.parametrize("name", [None, "explicit-name"])
@pytest.mark.parametrize("generated_index", [None, 1])
def test_resource_id_prefers_name_then_generated_name_over_labels(name: str | None, generated_index: int | None) -> None:
    resource = {
        "kind": "Job",
        "metadata": {"name": name, "generateName": "generated-", "labels": {"app": "example"}},
    }
    if generated_index is not None:
        resource[GENERATED_NAME_INDEX] = generated_index

    generated_name = "generated-" if generated_index is None else "generated-[1]"
    assert get_resource_id(resource) == f"Job.default.{name or generated_name}"


def test_generated_resources_have_context_and_distinct_graph_vertices(generated_manifest: Path) -> None:
    definitions, raw = create_definitions(root_folder=None, files=[str(generated_manifest)])
    kind = definitions[str(generated_manifest)][0]["kind"]
    context = build_definitions_context(definitions, raw)[str(generated_manifest)]
    graph = KubernetesLocalGraph(deepcopy(definitions))

    graph.build_graph(render_variables=False)

    names = ("first-[1]", "second-[2]")
    parent_ids = {f"{kind}.app.{name}" for name in names}
    assert set(context) == parent_ids
    vertices = {vertex.id: vertex for vertex in graph.vertices}
    if kind == "Pod":
        assert set(vertices) == parent_ids
    else:
        pod_ids = {f"Pod.app.{name}.app-example" for name in names}
        assert set(vertices) == parent_ids | pod_ids
        for name in names:
            pod = vertices[f"Pod.app.{name}.app-example"]
            assert pod.config[PARENT_RESOURCE_ID_KEY_NAME] == f"{kind}.app.{name}"
            assert pod.config["metadata"]["namespace"] == "app"


@pytest.mark.parametrize("graph_framework", GRAPH_FRAMEWORKS)
@pytest.mark.parametrize("suppressed", [False, True])
def test_runner_reports_generated_resources_with_source_context(
    generated_manifest: Path, graph_framework: str, suppressed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHECKOV_GRAPH_FRAMEWORK", graph_framework)
    if suppressed:
        generated_manifest.write_text(generated_manifest.read_text().replace(
            "  namespace: app\n",
            '  namespace: app\n  annotations:\n    checkov.io/skip1: CKV2_K8S_6=Test suppression\n',
        ))
    runner = Runner()

    report = runner.run(
        root_folder=None,
        files=[str(generated_manifest)],
        runner_filter=RunnerFilter(checks=["CKV_K8S_21", "CKV2_K8S_6"], show_progress_bar=False),
    )

    kind = runner.definitions[str(generated_manifest)][0]["kind"]
    names = ("first-[1]", "second-[2]")
    assert {(record.check_id, record.resource) for record in report.passed_checks} == {
        ("CKV_K8S_21", f"{kind}.app.{name}") for name in names
    }
    graph_records = report.skipped_checks if suppressed else report.failed_checks
    assert {(record.check_id, record.resource) for record in graph_records} == {
        ("CKV2_K8S_6", f"Pod.app.{name}" + ("" if kind == "Pod" else ".app-example"))
        for name in names
    }
    assert not (report.failed_checks if suppressed else report.skipped_checks)
    assert not report.parsing_errors
    for record, prefix in zip(sorted(graph_records, key=lambda record: record.resource), ("first-", "second-")):
        assert record.file_abs_path == str(generated_manifest)
        assert f"  generateName: {prefix}\n" in [line for _, line in record.code_block]
        assert record.file_line_range[0] > 0
        assert record.file_line_range[1] >= record.file_line_range[0]
        if suppressed:
            assert record.check_result["suppress_comment"] == "Test suppression"


@pytest.mark.parametrize("graph_framework", GRAPH_FRAMEWORKS)
def test_shared_generated_prefix_does_not_share_context_or_suppressions(
    generated_manifest: Path, graph_framework: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHECKOV_GRAPH_FRAMEWORK", graph_framework)
    first, second = generated_manifest.read_text().split("---\n")
    second = second.replace("second-", "first-").replace(
        "  namespace: app\n",
        '  namespace: app\n  annotations:\n    checkov.io/skip1: CKV2_K8S_6=Only second resource\n',
    )
    generated_manifest.write_text(first + "---\n" + second)
    runner = Runner()

    report = runner.run(
        root_folder=None,
        files=[str(generated_manifest)],
        runner_filter=RunnerFilter(checks=["CKV2_K8S_6"], show_progress_bar=False),
    )

    kind = runner.definitions[str(generated_manifest)][0]["kind"]
    second_start_line = 12 if kind == "Pod" else 17
    pod_suffix = "" if kind == "Pod" else ".app-example"
    assert len(report.failed_checks) == 1
    assert len(report.skipped_checks) == 1
    failed = report.failed_checks[0]
    skipped = report.skipped_checks[0]
    assert failed.resource == f"Pod.app.first-[1]{pod_suffix}"
    assert skipped.resource == f"Pod.app.first-[2]{pod_suffix}"
    assert failed.file_line_range[0] == 1
    assert skipped.file_line_range[0] == second_start_line
    assert skipped.check_result["suppress_comment"] == "Only second resource"
    assert set(runner.context[str(generated_manifest)]) == {
        f"{kind}.app.first-[1]", f"{kind}.app.first-[2]"
    }
    assert not report.passed_checks
    assert not report.parsing_errors


@pytest.mark.parametrize("graph_framework", GRAPH_FRAMEWORKS)
def test_generated_resources_connect_to_generated_network_policy(
    generated_manifest: Path, graph_framework: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHECKOV_GRAPH_FRAMEWORK", graph_framework)
    generated_manifest.write_text(
        generated_manifest.read_text()
        + "---\napiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\n"
        "metadata:\n  generateName: policy-\n  namespace: app\n"
        "spec:\n  podSelector: {}\n  policyTypes:\n    - Ingress\n"
    )
    runner = Runner()

    report = runner.run(
        root_folder=None,
        files=[str(generated_manifest)],
        runner_filter=RunnerFilter(checks=["CKV2_K8S_6"], show_progress_bar=False),
    )

    kind = runner.definitions[str(generated_manifest)][0]["kind"]
    names = ("first-[1]", "second-[2]")
    pod_suffix = "" if kind == "Pod" else ".app-example"
    assert {(record.check_id, record.resource) for record in report.passed_checks} == {
        ("CKV2_K8S_6", f"Pod.app.{name}{pod_suffix}") for name in names
    }
    assert len(report.passed_checks) == 2
    assert not report.failed_checks
    assert not report.skipped_checks
    assert not report.parsing_errors


@pytest.mark.parametrize("graph_framework", GRAPH_FRAMEWORKS)
def test_compact_json_list_keeps_generated_resource_suppressions_separate(
    tmp_path: Path, graph_framework: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHECKOV_GRAPH_FRAMEWORK", graph_framework)
    pod = {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"generateName": "same-", "namespace": "app"},
        "spec": {"containers": [{"name": "example", "image": "busybox:1.36"}]},
    }
    suppressed_pod = deepcopy(pod)
    suppressed_pod["metadata"]["annotations"] = {"checkov.io/skip1": "CKV2_K8S_6=Only second Pod"}
    path = tmp_path / "pods.json"
    path.write_text(json.dumps({"apiVersion": "v1", "kind": "List", "items": [pod, suppressed_pod]}))

    report = Runner().run(
        root_folder=None,
        files=[str(path)],
        runner_filter=RunnerFilter(checks=["CKV2_K8S_6"], show_progress_bar=False),
    )

    assert [(record.check_id, record.resource) for record in report.failed_checks] == [
        ("CKV2_K8S_6", "Pod.app.same-[1]")
    ]
    assert [(record.check_id, record.resource) for record in report.skipped_checks] == [
        ("CKV2_K8S_6", "Pod.app.same-[2]")
    ]
    assert report.skipped_checks[0].check_result["suppress_comment"] == "Only second Pod"
    assert not report.passed_checks
    assert not report.parsing_errors
