from checkov.terraform_json.parser import hclify, prepare_definition


def test_hclify():
    # given
    bucket_version = {
        "//": {
            "metadata": {
                "path": "AppStack/bucket_version",
                "uniqueId": "bucket_version",
            }
        },
        "bucket": "${aws_s3_bucket.bucket.bucket}",
        "versioning_configuration": {
            "status": "Enabled",
        },
    }

    # when
    result = hclify(obj=bucket_version)

    # then
    assert result == {
        "//": {
            "metadata": {
                "path": "AppStack/bucket_version",
                "uniqueId": "bucket_version",
            }
        },
        "bucket": ["${aws_s3_bucket.bucket.bucket}"],
        "versioning_configuration": [
            {
                "status": ["Enabled"],
            }
        ],
    }


def test_prepare_definition_provider_as_object():
    # Databricks-bundle / CDKTF style: provider config is a bare object instead of a list of objects.
    # Previously this crashed with `Exception: this method receives only dicts`.
    definition = {
        "provider": {
            "databricks": {
                "host": "https://example.cloud.databricks.com",
            }
        }
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {
        "provider": [
            {
                "databricks": {
                    "host": ["https://example.cloud.databricks.com"],
                }
            }
        ]
    }


def test_prepare_definition_provider_as_list():
    # The already-correct list-of-objects shape must keep working unchanged.
    definition = {
        "provider": {
            "aws": [
                {"region": "us-west-2"},
            ]
        }
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {
        "provider": [
            {
                "aws": {
                    "region": ["us-west-2"],
                }
            }
        ]
    }


def test_prepare_definition_provider_as_top_level_list_does_not_crash():
    # A top-level provider list (blocks is a list) previously raised AttributeError on `.items()`.
    definition = {
        "provider": [
            {"aws": {"region": "us-west-2"}},
        ]
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {"provider": []}


def test_prepare_definition_terraform_required_version_string_is_skipped():
    # `terraform.required_version` is a plain string; it must be skipped, not passed to hclify.
    definition = {
        "terraform": {
            "required_version": ">= 1.5.0",
        }
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {"terraform": []}


def test_prepare_definition_locals():
    cdk_definition = {
        "locals": {
            "bucket_name": "example",
            "http_endpoint": "disabled",
            "__startline__": 1,
            "__endline__": 2,
        }
    }

    # when
    tf_definition = prepare_definition(cdk_definition)

    # then
    assert tf_definition == {
        "locals": [
            {
                "bucket_name": ["example"],
                "http_endpoint": ["disabled"],
                "__startline__": 1,
                "__endline__": 2,
            }
        ]
    }
