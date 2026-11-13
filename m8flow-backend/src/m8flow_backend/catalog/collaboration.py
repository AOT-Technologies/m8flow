# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TypedDict

from lxml import etree

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
MESSAGE_EVENT_PARENTS = {
    BPMN + name
    for name in (
        "startEvent",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "endEvent",
    )
}


def is_bpmn_event_definition(tag: object) -> bool:
    return (
        isinstance(tag, str)
        and tag.startswith(BPMN)
        and tag.endswith(("EventDefinition", "}eventDefinitionRef"))
    )


class CollaborationParticipant(TypedDict):
    id: str
    name: str
    startable: bool


def collaboration_participants(source: str) -> list[CollaborationParticipant] | None:
    """Preview executable participants of the primary BPMN for the Start picker."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(source.encode("utf-8"), parser)
    except etree.XMLSyntaxError:
        return None
    if root.getroottree().docinfo.doctype:
        return None
    collaborations = root.findall(BPMN + "collaboration")
    if len(collaborations) != 1:
        return None
    processes = {
        node.get("id"): node
        for node in root.findall(BPMN + "process")
        if node.get("id")
    }
    namespace = root.get("targetNamespace")
    seen_process_ids: set[str] = set()
    participants: list[CollaborationParticipant] = []
    for participant in collaborations[0].findall(BPMN + "participant"):
        process_id = participant.get("processRef")
        if process_id is None:
            continue  # Black-box pool.
        if ":" in process_id:
            prefix, process_id = process_id.split(":", 1)
            # Core resolves qualified references only within this document.
            if namespace is None or participant.nsmap.get(prefix) != namespace:
                return None
        process = processes.get(process_id)
        if process is None or process_id in seen_process_ids:
            return None
        seen_process_ids.add(process_id)
        if process.get("isExecutable") not in {"true", "1"}:
            continue
        participants.append(
            {
                "id": process_id,
                "name": participant.get("name") or process.get("name") or process_id,
                "startable": any(
                    not any(is_bpmn_event_definition(child.tag) for child in event)
                    for event in process.findall(BPMN + "startEvent")
                ),
            }
        )
    return participants if len(participants) >= 2 else None
