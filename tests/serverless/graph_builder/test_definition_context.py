from checkov.serverless.graph_builder.definition_context import build_definitions_context


def test_build_definitions_context_skips_resource_without_line_metadata():
    # given
    file_path = "serverless.yml"
    definitions = {
        file_path: {
            "custom": {
                "entry": {
                    "value": "without parser line metadata",
                }
            }
        }
    }
    definitions_raw = {file_path: [(1, "custom:\n"), (2, "  entry: value\n")]}

    # when
    context = build_definitions_context(definitions=definitions, definitions_raw=definitions_raw)

    # then
    assert context == {file_path: {"custom": {}}}
