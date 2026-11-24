"""Pure-Python reference model for the blueprint's discovery contract."""


def is_supported_zigbee(identifiers) -> bool:
    """Recognize ZHA and Zigbee2MQTT device-registry identifiers."""
    if not identifiers or isinstance(identifiers, (str, bytes)):
        return False
    for identifier in identifiers:
        if isinstance(identifier, (str, bytes)):
            continue
        try:
            parts = list(identifier)
        except TypeError:
            continue
        if not parts:
            continue
        namespace = str(parts[0]).casefold()
        value = str(parts[1]).casefold() if len(parts) > 1 else ""
        if namespace == "zha" or (namespace == "mqtt" and "zigbee2mqtt" in value):
            return True
    return False


def classify_updates(configured_domains, update_devices, identifiers_by_device, entities_by_device):
    """Return update entity IDs per configured row using first-domain ownership."""
    normalized_domains = [str(domain).casefold() for domain in configured_domains]
    result = [[] for _ in normalized_domains]
    seen_updates = set()

    for update_entity in sorted(update_devices):
        if update_entity in seen_updates:
            continue
        seen_updates.add(update_entity)
        device = update_devices[update_entity]
        if not device or not is_supported_zigbee(identifiers_by_device.get(device)):
            continue
        sibling_domains = {
            str(entity_id).split(".", 1)[0].casefold()
            for entity_id in entities_by_device.get(device, ())
            if isinstance(entity_id, str) and "." in entity_id
        }
        owner = next(
            (index for index, domain in enumerate(normalized_domains) if domain in sibling_domains),
            None,
        )
        if owner is not None:
            result[owner].append(update_entity)
    return result
