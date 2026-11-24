from pathlib import Path

import pytest
import yaml
from yaml.nodes import ScalarNode


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


def test_yaml_parses_and_is_an_automation_blueprint():
    data = load_blueprint()
    assert data["blueprint"]["domain"] == "automation"
    assert data["blueprint"]["homeassistant"]["min_version"] == "2025.8.0"


def test_object_selector_supports_unbounded_ordered_classes_and_fields():
    inputs = load_blueprint()["blueprint"]["input"]
    assert set(inputs) == {"device_classes", "presence_trackers", "install_timeout"}

    selector = inputs["device_classes"]["selector"]["object"]
    assert selector["multiple"] is True
    assert selector["label_field"] == "name"
    fields = selector["fields"]
    assert set(fields) == {
        "name",
        "update_entities",
        "update_start",
        "update_end",
        "quiet_enabled",
        "quiet_start",
        "quiet_end",
    }
    assert all(fields[name]["required"] is True for name in ("name", "update_entities", "update_start", "update_end"))
    updates = fields["update_entities"]["selector"]["entity"]
    assert updates["multiple"] is True
    assert updates["reorder"] is True
    assert updates["filter"]["domain"] == "update"


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


def test_nested_repeats_serialize_classes_then_entities():
    outer, inner = outer_and_inner_repeats(load_blueprint())
    assert outer["for_each"] == "{{ device_classes }}"
    assert inner["for_each"] == "{{ class_update_entities }}"


def test_outer_repeat_item_is_snapshotted_before_inner_repeat():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    snapshot = outer["sequence"][0]["variables"]
    assert snapshot["current_class"] == "{{ repeat.item }}"
    class_fields = outer["sequence"][1]["variables"]
    assert class_fields["class_update_entities"] == "{{ current_class['update_entities'] }}"
    assert all("repeat.item" not in str(value) for value in class_fields.values())


def test_classes_are_skipped_with_if_not_a_bare_condition():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    assert "if" in outer["sequence"][2]
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
    ("prefix", "required_fragment"),
    [
        ("update", "(start == end)"),
        ("update", "(start < end and start <= current < end)"),
        ("update", "(start > end and (current >= start or current < end))"),
        ("quiet", "(quiet_start == quiet_end)"),
        ("quiet", "quiet_start < quiet_end and quiet_start <= current < quiet_end"),
        ("quiet", "quiet_start > quiet_end and (current >= quiet_start or current < quiet_end)"),
    ],
)
def test_time_templates_cover_all_day_normal_and_midnight_windows(prefix, required_fragment):
    assert required_fragment in gate_template(load_blueprint())


def test_outer_prefilter_and_per_entity_gate_use_same_safety_contract():
    outer, _ = outer_and_inner_repeats(load_blueprint())
    prefilter = outer["sequence"][2]["if"][0]["value_template"]
    item_gate = gate_template(load_blueprint())
    for fragment in (
        "start == end",
        "quiet_start == quiet_end",
        "not is_state(tracker, 'home')",
        "in_update and not in_quiet and trackers.all_home",
    ):
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
    assert "wait_template" in wait
    assert wait["wait_template"] == "{{ is_state(current_update_entity, 'off') }}"
    assert wait["timeout"] == InputRef("install_timeout")
    assert wait["continue_on_timeout"] is False
    assert len(branch) == install_index + 2


def test_no_delay_or_legacy_inputs_remain():
    data = load_blueprint()
    assert not any("delay" in node for node in walk(data))
    text = BLUEPRINT.read_text(encoding="utf-8").casefold()
    for legacy in ("inter_device_delay", "device_class_name", "start_time", "end_time"):
        assert legacy not in text



def test_no_cancel_action_can_interrupt_running_update():
    data = load_blueprint()
    forbidden = {"update.skip", "homeassistant.restart", "automation.turn_off"}
    assert not forbidden.intersection(node.get("action") for node in walk(data))


def test_readme_documents_priority_latency_tracker_and_migration_contracts():
    readme = README.read_text(encoding="utf-8")
    for fragment in (
        "eine Blueprint-Instanz",
        "Klassenreihenfolge",
        "Entity-Reihenfolge",
        "maximal etwa eine Minute",
        "ALLE",
        "unknown",
        "unavailable",
        "start == end",
        "Migration",
        "Home Assistant 2025.8.0",
    ):
        assert fragment in readme
