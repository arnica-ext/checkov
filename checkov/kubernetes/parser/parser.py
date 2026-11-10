from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from yaml import YAMLError

from checkov.common.resource_code_logger_filter import add_resource_code_filter_to_logger
from checkov.kubernetes.parser import k8_yaml, k8_json
from checkov.kubernetes.parser.validatior import K8sValidator

logger = logging.getLogger(__name__)
add_resource_code_filter_to_logger(logger)

GENERATED_NAME_INDEX = "_checkov_generated_name_index"


def _set_generated_name_indices(value: Any, next_index: int = 1) -> int:
    """Index generated resources in depth-first order, visiting each container once."""
    # Iterators preserve traversal order without copying wide containers onto the stack.
    pending: list[Iterator[Any]] = [iter((value,))]
    visited: set[int] = set()
    while pending:
        try:
            current = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue

        if not isinstance(current, (dict, list)) or id(current) in visited:
            continue
        # YAML aliases can revisit a container or form a cycle.
        visited.add(id(current))

        if isinstance(current, dict):
            metadata = current.get("metadata")
            if isinstance(metadata, dict) and metadata.get("generateName") and not metadata.get("name"):
                current[GENERATED_NAME_INDEX] = next_index
                next_index += 1
            pending.append(iter(current.values()))
        else:
            pending.append(iter(current))
    return next_index


def parse(filename: str) -> tuple[list[dict[str, Any]], list[tuple[int, str]]] | None:
    template = None
    template_lines: "list[tuple[int, str]]" = []
    valid_templates = []
    try:
        if filename.endswith((".yaml", ".yml")):
            (template, template_lines) = k8_yaml.load(Path(filename))
        if filename.endswith(".json"):
            (template, template_lines) = k8_json.load(Path(filename))
        if template:
            if isinstance(template, list):
                for i, t in enumerate(template):
                    is_valid, reason = K8sValidator.is_valid_template(t)
                    if is_valid:
                        valid_templates.append(t)
                    else:
                        logging.debug(f"template {i} from file {filename} is not a valid k8s template, reason: {reason}")
            else:
                return None
        else:
            return None
    except IOError as e:
        if e.errno == 2:
            logger.error('Template file not found: %s', filename)
            return None
        elif e.errno == 21:
            logger.error('Template references a directory, not a file: %s',
                         filename)
            return None
        elif e.errno == 13:
            logger.error('Permission denied when accessing template file: %s',
                         filename)
            return None
    except UnicodeDecodeError:
        logger.error('Cannot read file contents: %s', filename)
        return None
    except YAMLError:
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            logger.debug('Cannot read file contents: %s - is it a yaml?', filename)
        return None

    _set_generated_name_indices(valid_templates)
    return valid_templates, template_lines
