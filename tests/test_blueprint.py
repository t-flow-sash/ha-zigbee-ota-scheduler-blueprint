from pathlib import Path

import pytest
import yaml
from yaml.nodes import ScalarNode


ROOT = Path(__file__).parents[1]
BLUEPRINT = ROOT / "blueprints" / "automation" / "zigbee_ota_scheduler" / "sequential_ota_by_class.yaml"


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


def all_actions(data: dict, action_name: str) -> list[dict]:
    return [node for node in walk(data) if node.get("action") == action_name]


def repeat_block(data: dict) -> dict:
    repeats = [node["repeat"] for node in walk(data) if "repeat" in node]
    assert len(repeats) == 1
    return repeats[0]


def install_branch(data: dict) -> list[dict]:
    repeat = repeat_block(data)
    choices = [node for node in repeat["sequence"] if "if" in node]
    assert len(choices) == 1
    return choices[0]["then"]


def test_yaml_parses_and_is_an_automation_blueprint():
    data = load_blueprint()
    assert data["blueprint"]["domain"] == "automation"
    assert data["blueprint"]["homeassistant"]["min_version"]


def test_required_inputs_and_update_entity_selector():
    inputs = load_blueprint()["blueprint"]["input"]
    assert {"device_class_name", "update_entities", "start_time", "end_time", "install_timeout", "inter_device_delay"} <= inputs.keys()
    selector = inputs["update_entities"]["selector"]["entity"]
    assert selector["multiple"] is True
    assert selector["reorder"] is True
    assert selector["filter"]["domain"] == "update"


def test_daily_start_trigger_uses_configured_start_time_only():
    data = load_blueprint()
    assert data["triggers"] == [{"trigger": "time", "at": InputRef("start_time")}]


def test_mode_single_prevents_overlapping_runs():
    data = load_blueprint()
    assert data["mode"] == "single"
    assert data["max_exceeded"] == "silent"


def test_entities_are_processed_by_one_sequential_for_each_loop():
    data = load_blueprint()
    repeat = repeat_block(data)
    assert repeat["for_each"] == InputRef("update_entities")
    assert not any("parallel" in node for node in walk(data))
    assert len(all_actions(data, "update.install")) == 1


def test_window_is_checked_for_every_item_before_install_branch():
    sequence = repeat_block(load_blueprint())["sequence"]
    assert sequence[0]["condition"] == "time"
    assert sequence[0]["after"] == InputRef("start_time")
    assert sequence[0]["before"] == InputRef("end_time")
    assert "if" in sequence[1]


def test_only_exact_on_state_enters_install_branch():
    gate = repeat_block(load_blueprint())["sequence"][1]
    condition = gate["if"][0]
    assert condition["condition"] == "template"
    template = condition["value_template"]
    assert "is_state(repeat.item, 'on')" in template
    for unsafe in ("!= 'off'", "not is_state(repeat.item, 'off')"):
        assert unsafe not in template


def test_install_targets_only_current_repeat_item():
    installs = all_actions(load_blueprint(), "update.install")
    assert installs[0]["target"] == {"entity_id": "{{ repeat.item }}"}


def test_install_is_followed_by_fail_closed_completion_wait():
    branch = install_branch(load_blueprint())
    install_index = next(i for i, step in enumerate(branch) if step.get("action") == "update.install")
    wait = branch[install_index + 1]
    assert "wait_template" in wait
    assert "is_state(repeat.item, 'off')" in wait["wait_template"]
    assert "not is_state" not in wait["wait_template"]
    assert wait["timeout"] == InputRef("install_timeout")
    assert wait["continue_on_timeout"] is False


def test_delay_occurs_only_after_successful_wait():
    branch = install_branch(load_blueprint())
    wait_index = next(i for i, step in enumerate(branch) if "wait_template" in step)
    delay_index = next(i for i, step in enumerate(branch) if "delay" in step)
    assert delay_index == wait_index + 1
    assert branch[delay_index]["delay"] == InputRef("inter_device_delay")


def test_no_end_trigger_or_cancel_action_can_interrupt_running_update():
    data = load_blueprint()
    assert all(trigger.get("at") != InputRef("end_time") for trigger in data["triggers"])
    forbidden = {"update.skip", "homeassistant.restart", "automation.turn_off"}
    assert not forbidden.intersection(node.get("action") for node in walk(data))


@pytest.mark.parametrize("bad_state", ["off", "unknown", "unavailable"])
def test_documented_skip_states_are_not_install_predicates(bad_state):
    template = repeat_block(load_blueprint())["sequence"][1]["if"][0]["value_template"]
    assert f"'{bad_state}'" not in template
