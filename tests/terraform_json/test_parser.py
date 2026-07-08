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
    definition = {
        "provider": {
            "my_provider": {
                "some_attribute": "some_value",
            }
        }
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {
        "provider": [
            {
                "my_provider": {
                    "some_attribute": ["some_value"],
                }
            }
        ]
    }


def test_prepare_definition_provider_as_list():
    definition = {
        "provider": {
            "my_provider": [
                {"some_attribute": "some_value"},
            ]
        }
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {
        "provider": [
            {
                "my_provider": {
                    "some_attribute": ["some_value"],
                }
            }
        ]
    }


def test_prepare_definition_provider_as_top_level_list_does_not_crash():
    definition = {
        "provider": [
            {"my_provider": {"some_attribute": "some_value"}},
        ]
    }

    tf_definition = prepare_definition(definition)

    assert tf_definition == {"provider": []}


def test_prepare_definition_terraform_required_version_string_is_skipped():
    definition = {
        "terraform": {
            "required_version": ">= 1.0.0",
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
