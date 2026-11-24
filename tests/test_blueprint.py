from pathlib import Path

import pytest
import yaml
from yaml.nodes import ScalarNode

from discovery_reference import classify_updates, is_supported_zigbee


ROOT = Path(__file__).parents[1]
BLUEPRINT = ROOT / "blueprints" / "automation" / "zigbee_ota_scheduler" / "sequential_ota_by_class.yaml"
README = ROOT / "README.md"


class InputRef(str):
    """Preserve Home Assistant's !input references while parsing YAML."""


class BlueprintLoader(yaml.SafeLoader):
    pass


def _input(loader: BlueprintLoader, node: ScalarNode) -> InputRef:
    return InputRef(loader.construct_scalar(node))


BlueprintLoader.add_constructor("!input", _input)


def load_blueprint() -> dict:
    with BLUEPRINT.open(encoding="utf-8") as stream:
        return yaml.load(stream, Loader=BlueprintLoader)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def repeat_blocks(data: dict) -> list[dict]:
    return [node["repeat"] for node in walk(data) if "repeat" in node]


def outer_and_inner_repeats(data: dict) -> tuple[dict, dict]:
    repeats = repeat_blocks(data)
    assert len(repeats) == 2
    outer = next(block for block in repeats if "device_classes" in str(block["for_each"]))
    inner = next(block for block in repeats if "class_update_entities" in str(block["for_each"]))
    return outer, inner


def all_actions(data: dict, action_name: str) -> list[dict]:
    return [node for node in walk(data) if node.get("action") == action_name]


def install_branch(data: dict) -> list[dict]:
    _, inner = outer_and_inner_repeats(data)
    gates = [node for node in inner["sequence"] if "if" in node]
    assert len(gates) == 1
    return gates[0]["then"]


def gate_template(data: dict) -> str:
    _, inner = outer_and_inner_repeats(data)
    gate = next(node for node in inner["sequence"] if "if" in node)
    return gate["if"][0]["value_template"]


def class_variables(data: dict) -> dict:
    outer, _ = outer_and_inner_repeats(data)
    return next(step["variables"] for step in outer["sequence"] if "class_update_entities" in step.get("variables", {}))


def test_yaml_parses_and_is_an_automation_blueprint():
    data = load_blueprint()
    assert data["blueprint"]["domain"] == "automation"
    assert data["blueprint"]["homeassistant"]["min_version"] == "2025.8.0"


def test_object_selector_uses_domain_and_never_manual_update_entities():
    inputs = load_blueprint()["blueprint"]["input"]
    assert set(inputs) == {"device_classes", "presence_trackers", "install_timeout"}
    selector = inputs["device_classes"]["selector"]["object"]
    assert selector["multiple"] is True
    assert selector["label_field"] == "name"
    assert selector["description_field"] == "domain"
    fields = selector["fields"]
    assert set(fields) == {
        "name", "domain", "update_start", "update_end",
        "quiet_enabled", "quiet_start", "quiet_end",
    }
    assert "update_entities" not in fields
    assert all(fields[name]["required"] is True for name in ("name", "domain", "update_start", "update_end"))
    domain_selector = fields["domain"]["selector"]["select"]
    assert domain_selector["custom_value"] is True
    values = {option["value"] for option in domain_selector["options"]}
    assert {"light", "climate", "switch", "cover", "binary_sensor", "sensor"} <= values


def test_optional_trackers_are_multiple_device_trackers_with_empty_default():
    tracker_input = load_blueprint()["blueprint"]["input"]["presence_trackers"]
    assert tracker_input["default"] == []
    selector = tracker_input["selector"]["entity"]
    assert selector["multiple"] is True
    assert selector["filter"]["domain"] == "device_tracker"


def test_minute_and_home_assistant_start_triggers():
    triggers = load_blueprint()["triggers"]
    assert {"trigger": "time_pattern", "minutes": "/1"} in triggers
    assert {"trigger": "homeassistant", "event": "start"} in triggers
    assert len(triggers) == 2


def test_mode_single_prevents_overlapping_runs():
    data = load_blueprint()
    assert data["mode"] == "single"
    assert data["max_exceeded"] == "silent"
    assert not any("parallel" in node for node in walk(data))


def test_inputs_are_copied_to_variables_before_dynamic_use():
    variables = load_blueprint()["variables"]
    assert variables["device_classes"] == InputRef("device_classes")
    assert variables["presence_trackers"] == InputRef("presence_trackers")


def test_nested_repeats_serialize_classes_then_discovered_entities():
    outer, inner = outer_and_inner_repeats(load_blueprint())
    assert outer["for_each"] == "{{ device_classes }}"
    assert inner["for_each"] == "{{ class_update_entities }}"


def test_outer_repeat_item_and_index_are_snapshotted_before_inner_repeat():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    snapshot = outer["sequence"][0]["variables"]
    assert snapshot["current_class"] == "{{ repeat.item }}"
    assert snapshot["current_class_index"] == "{{ repeat.index }}"
    fields = class_variables(load_blueprint())
    assert "current_class['domain']" in fields["class_domain"]
    assert all("repeat.item" not in str(value) for value in fields.values())


def test_discovery_uses_live_registry_template_functions_and_safe_identifier_checks():
    template = class_variables(load_blueprint())["class_update_entities"]
    for fragment in (
        "states.update", "device_id(", "device_attr(", "'identifiers'", "device_entities(",
        "identifier is iterable", "identifier is not string", "identifier | length",
        "identifier_namespace == 'zha'", "identifier_namespace == 'mqtt'", "'zigbee2mqtt' in value",
    ):
        assert fragment in template


def test_discovery_first_configured_matching_domain_and_dedup_contract_is_static():
    template = class_variables(load_blueprint())["class_update_entities"]
    assert "for configured_class in device_classes" in template
    assert "owner.index is none" in template
    assert "configured_domain in sibling_domains.values" in template
    assert "owner.index == (current_class_index | int)" in template
    assert "update_entity not in result.entities" in template
    assert "split('.', 1)[0]" in template


def test_classes_are_skipped_with_if_not_a_bare_condition():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    prefilter = [step for step in outer["sequence"] if "if" in step]
    assert len(prefilter) == 1
    assert not any(step.get("condition") for step in outer["sequence"])


def test_gate_rechecks_window_quiet_trackers_and_exact_on_before_each_install():
    template = gate_template(load_blueprint())
    assert "class_update_start" in template and "class_update_end" in template
    assert "class_quiet_enabled" in template
    assert "class_quiet_start" in template and "class_quiet_end" in template
    assert "for tracker in presence_trackers" in template
    assert "not is_state(tracker, 'home')" in template
    assert "is_state(current_update_entity, 'on')" in template
    assert "in_update and not in_quiet and trackers.all_home" in template


@pytest.mark.parametrize(
    "required_fragment",
    [
        "(start == end)",
        "(start < end and start <= current < end)",
        "(start > end and (current >= start or current < end))",
        "(quiet_start == quiet_end)",
        "quiet_start < quiet_end and quiet_start <= current < quiet_end",
        "quiet_start > quiet_end and (current >= quiet_start or current < quiet_end)",
    ],
)
def test_time_templates_cover_all_day_normal_and_midnight_windows(required_fragment):
    assert required_fragment in gate_template(load_blueprint())


def test_outer_prefilter_and_per_entity_gate_use_same_safety_contract():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    prefilter = next(step["if"][0]["value_template"] for step in outer["sequence"] if "if" in step)
    item_gate = gate_template(load_blueprint())
    for fragment in ("start == end", "quiet_start == quiet_end", "not is_state(tracker, 'home')", "in_update and not in_quiet and trackers.all_home"):
        assert fragment in prefilter
        assert fragment in item_gate


def test_install_targets_only_snapshotted_current_entity():
    installs = all_actions(load_blueprint(), "update.install")
    assert len(installs) == 1
    assert installs[0]["target"] == {"entity_id": "{{ current_update_entity }}"}


def test_install_is_immediately_followed_by_fail_closed_completion_wait():
    branch = install_branch(load_blueprint())
    install_index = next(i for i, step in enumerate(branch) if step.get("action") == "update.install")
    wait = branch[install_index + 1]
    assert wait["wait_template"] == "{{ is_state(current_update_entity, 'off') }}"
    assert wait["timeout"] == InputRef("install_timeout")
    assert wait["continue_on_timeout"] is False
    assert len(branch) == install_index + 2


def test_no_delay_manual_entity_input_or_cancel_action_remains():
    data = load_blueprint()
    assert not any("delay" in node for node in walk(data))
    forbidden = {"update.skip", "homeassistant.restart", "automation.turn_off"}
    assert not forbidden.intersection(node.get("action") for node in walk(data))
    assert "current_class['update_entities']" not in BLUEPRINT.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("identifiers", "expected"),
    [
        ({("zha", "00:11")}, True),
        ({("ZHA", "00:11")}, True),
        ({("mqtt", "zigbee2mqtt_0x123")}, True),
        ({("MQTT", "Kitchen/ZigBee2MQTT/device")}, True),
        ({("mqtt", "other-device")}, False),
        ({("matter", "zigbee2mqtt")}, False),
        ({("zha",)}, True),
        ({()}, False),
        (None, False),
        ("zha", False),
    ],
)
def test_identifier_reference_matrix(identifiers, expected):
    assert is_supported_zigbee(identifiers) is expected


def test_reference_classification_prioritizes_first_matching_domain_and_skips_others():
    updates = {
        "update.climate_sensor": "dev-both",
        "update.light": "dev-light",
        "update.no_device": None,
        "update.non_zigbee": "dev-mqtt-other",
        "update.no_domain_match": "dev-button",
    }
    identifiers = {
        "dev-both": {("zha", "a")},
        "dev-light": {("mqtt", "bridge/zigbee2mqtt/light")},
        "dev-mqtt-other": {("mqtt", "unrelated")},
        "dev-button": {("zha", "b")},
    }
    entities = {
        "dev-both": {"climate.room", "sensor.temperature", "update.climate_sensor"},
        "dev-light": {"light.room", "sensor.linkquality", "update.light"},
        "dev-button": {"button.identify", "update.no_domain_match"},
    }
    result = classify_updates(["climate", "light", "sensor"], updates, identifiers, entities)
    assert result == [["update.climate_sensor"], ["update.light"], []]


def test_reference_duplicate_domain_rows_do_not_duplicate_updates():
    result = classify_updates(
        ["light", "light", "sensor"],
        {"update.one": "dev"},
        {"dev": {("zha", "id")}},
        {"dev": {"light.one", "sensor.one", "update.one"}},
    )
    assert result == [["update.one"], [], []]


def test_readme_documents_discovery_priority_limits_and_breaking_migration():
    readme = README.read_text(encoding="utf-8")
    for fragment in (
        "eine Blueprint-Instanz", "states.update", "device_id", "device_attr", "device_entities",
        "ZHA", "Zigbee2MQTT", "erste passende konfigurierte Domain", "keine kanonische Primary-Domain",
        "climate vor sensor", "light vor sensor", "binary_sensor vor sensor",
        "Geräte ohne Device-ID", "Nicht-Zigbee", "maximal etwa eine Minute", "ALLE",
        "unknown", "unavailable", "start == end", "Breaking Migration", "Home Assistant 2025.8.0",
    ):
        assert fragment in readme
