"""Process-instance helpers for the next-gen backend (``/v1.0/m8flow/process-instances``).

Instances are addressed by their bare id; no process-model-qualified paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.api_client import M8flowAPIClient

INSTANCES = "/v1.0/m8flow/process-instances"
_MAX_PER_PAGE = 100  # backend cap


async def get_instance(client: M8flowAPIClient, process_instance_id: int, token: str) -> dict[str, Any]:
    """Instance detail: metadata, ``bpmn_xml`` and ``tasks`` ([{bpmn_identifier, state}])."""
    return await client.get(f"{INSTANCES}/{int(process_instance_id)}", token)


async def list_instances(
    client: M8flowAPIClient,
    token: str,
    *,
    process_model_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """List instances as ``{"results": [...], "pagination": {count, total, pages}}``.

    The backend has no exact process-model filter, only ``search`` (a substring match on
    the model id / display name). With ``process_model_id`` every search hit is fetched,
    filtered to the exact model, and paginated locally so totals stay correct.
    """
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if not process_model_id:
        params.update(page=max(page, 1), per_page=min(max(per_page, 1), _MAX_PER_PAGE))
        return await client.get(INSTANCES, token, params=params)

    # ponytail: pulls every search hit for the model; add a backend model filter if this gets slow.
    params.update(search=process_model_id, per_page=_MAX_PER_PAGE)
    rows: list[dict[str, Any]] = []
    fetch_page = 1
    while True:
        result = await client.get(INSTANCES, token, params={**params, "page": fetch_page})
        rows += [r for r in result.get("results", []) if r.get("process_model_identifier") == process_model_id]
        if fetch_page >= int(result.get("pagination", {}).get("pages") or 0):
            break
        fetch_page += 1
    return paginate(rows, page, per_page)


FINISHED_STATUSES = frozenset({"complete", "terminated", "error"})


async def delete_instance(client: M8flowAPIClient, process_instance_id: int, token: str) -> dict[str, Any]:
    """Permanently delete a finished instance (backend returns 409 for active ones)."""
    return await client.delete(f"{INSTANCES}/{int(process_instance_id)}", token)


async def purge_model_instances(
    client: M8flowAPIClient, token: str, process_model_id: str, *, terminate_active: bool = False
) -> tuple[int, list[str]]:
    """Delete every instance of one process model so the model itself can be deleted.

    Finished instances are deleted. Active/suspended ones are terminated first when
    ``terminate_active`` is set, otherwise left in place and reported.

    Returns:
        (deleted_count, problems)
    """
    listing = await list_instances(client, token, process_model_id=process_model_id, per_page=_MAX_PER_PAGE)
    rows = list(listing.get("results", []))
    pages = int(listing.get("pagination", {}).get("pages") or 1)
    for page in range(2, pages + 1):
        more = await list_instances(client, token, process_model_id=process_model_id, page=page, per_page=_MAX_PER_PAGE)
        rows += more.get("results", [])
    deleted, problems = 0, []
    for row in rows:
        instance_id, status = row.get("id"), row.get("status")
        try:
            if status not in FINISHED_STATUSES:
                if not terminate_active:
                    problems.append(f"instance {instance_id} is {status}")
                    continue
                await client.post(f"{INSTANCES}/{int(instance_id)}/terminate", token)
            await delete_instance(client, instance_id, token)
            deleted += 1
        except Exception as e:
            problems.append(f"instance {instance_id}: {e}")
    return deleted, problems


def paginate(rows: list[Any], page: int, per_page: int) -> dict[str, Any]:
    """Slice an unpaginated backend list into the ``{results, pagination}`` shape tools return."""
    page, per_page = max(page, 1), max(per_page, 1)
    start = (page - 1) * per_page
    results = rows[start : start + per_page]
    return {
        "results": results,
        "pagination": {"count": len(results), "total": len(rows), "pages": -(-len(rows) // per_page)},
    }
