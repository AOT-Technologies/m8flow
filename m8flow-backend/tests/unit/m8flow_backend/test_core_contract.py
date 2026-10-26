"""Contract between the host and the pinned ``m8flow-core`` wheel.

Run this first after swapping the wheel: it fails on the exact symbol, column,
keyword, or command key that moved, instead of a downstream 500 or a silently
widened authorization decision.

The import, attribute, and call-shape checks are derived from the host source
at collection time, so new host usage of core is pinned without editing this
file. The remaining tests pin couplings that the source scan cannot see:
string protocols (command keys, status values), the error hierarchy, and the
private core hooks the host wraps.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from m8flow_core import api
from m8flow_core import errors as core_errors

SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "m8flow_backend"
CORE_PACKAGE = "m8flow_core"


@dataclass(frozen=True)
class _Binding:
    module: str
    name: str | None  # None for `import m8flow_core.x` (module import)


@dataclass(frozen=True)
class _Use:
    file: str
    line: int
    local: str
    binding: _Binding
    attr: str | None = None
    positional: int = 0
    keywords: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        target = self.local if self.attr is None else f"{self.local}.{self.attr}"
        return f"{self.file}:{self.line}:{target}"


def _core_bindings(tree: ast.AST) -> dict[str, _Binding]:
    bindings: dict[str, _Binding] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == CORE_PACKAGE:
            for alias in node.names:
                bindings[alias.asname or alias.name] = _Binding(node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == CORE_PACKAGE:
                    bindings[alias.asname or alias.name] = _Binding(alias.name, None)
    return bindings


def _scan_host_source() -> tuple[list[_Use], list[_Use], list[_Use]]:
    imports: list[_Use] = []
    attributes: dict[tuple[str, str, str], _Use] = {}
    calls: list[_Use] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bindings = _core_bindings(tree)
        if not bindings:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                for local, binding in bindings.items():
                    names = {a.asname or a.name for a in node.names}
                    if local in names and (
                        (isinstance(node, ast.ImportFrom) and node.module == binding.module)
                        or (isinstance(node, ast.Import) and binding.name is None)
                    ):
                        imports.append(_Use(rel, node.lineno, local, binding))
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in bindings
                and bindings[node.value.id].name is not None
            ):
                key = (rel, node.value.id, node.attr)
                attributes.setdefault(
                    key, _Use(rel, node.lineno, node.value.id, bindings[node.value.id], node.attr)
                )
            elif isinstance(node, ast.Call):
                if any(isinstance(a, ast.Starred) for a in node.args) or any(
                    k.arg is None for k in node.keywords
                ):
                    continue  # *args / **kwargs: shape unknowable statically
                func = node.func
                if isinstance(func, ast.Name) and func.id in bindings:
                    local, attr = func.id, None
                elif (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id in bindings
                ):
                    local, attr = func.value.id, func.attr
                else:
                    continue
                if bindings[local].name is None:
                    continue
                calls.append(
                    _Use(
                        rel,
                        node.lineno,
                        local,
                        bindings[local],
                        attr,
                        positional=len(node.args),
                        keywords=tuple(k.arg for k in node.keywords),
                    )
                )
    # Dedupe imports (a name imported in several functions of one file is one use per line).
    unique_imports = list({(u.file, u.line, u.local): u for u in imports}.values())
    return unique_imports, list(attributes.values()), calls


IMPORT_USES, ATTRIBUTE_USES, CALL_USES = _scan_host_source()


def _resolve(binding: _Binding) -> Any:
    module = importlib.import_module(binding.module)
    if binding.name is None:
        return module
    if hasattr(module, binding.name):
        return getattr(module, binding.name)
    # `from package import submodule`
    return importlib.import_module(f"{binding.module}.{binding.name}")


def _target(use: _Use) -> Any:
    obj = _resolve(use.binding)
    return obj if use.attr is None else getattr(obj, use.attr)


def test_source_scan_finds_the_host_core_surface():
    # Guards the scanner itself: a broken walk would make every derived test vacuous.
    assert len(IMPORT_USES) > 50
    assert len(ATTRIBUTE_USES) > 50
    assert len(CALL_USES) > 20
    imported = {(u.binding.module, u.binding.name) for u in IMPORT_USES}
    assert ("m8flow_core", "api") in imported
    assert ("m8flow_core.models.process_instance", "ProcessInstanceModel") in imported
    assert ("m8flow_core.services.authorization", "grant_permission_to_group") in imported


@pytest.mark.parametrize("use", IMPORT_USES, ids=lambda u: u.id)
def test_every_core_import_in_host_source_resolves(use: _Use):
    _resolve(use.binding)


@pytest.mark.parametrize("use", ATTRIBUTE_USES, ids=lambda u: u.id)
def test_every_core_attribute_the_host_reads_exists(use: _Use):
    owner = _resolve(use.binding)
    assert hasattr(owner, use.attr), (
        f"{use.binding.module}.{use.binding.name} has no attribute {use.attr!r} "
        f"(used at {use.file}:{use.line})"
    )


@pytest.mark.parametrize("use", CALL_USES, ids=lambda u: u.id)
def test_every_core_call_in_host_source_matches_its_signature(use: _Use):
    target = _target(use)
    if hasattr(target, "__mapper__"):
        # Declarative ORM constructors take **kwargs; each one must be a mapped attribute.
        missing = [kw for kw in use.keywords if not hasattr(target, kw)]
        assert not missing, f"{target.__name__} has no attributes {missing} (used at {use.file}:{use.line})"
        return
    if inspect.isclass(target) and issubclass(target, BaseException) and "__init__" not in vars(target):
        # BaseException.__init__ takes *args and has no introspectable signature.
        assert use.keywords == (), f"{target.__name__} takes no keywords (used at {use.file}:{use.line})"
        return
    signature = inspect.signature(target)
    placeholder = object()
    try:
        signature.bind(*[placeholder] * use.positional, **{kw: placeholder for kw in use.keywords})
    except TypeError as exc:
        pytest.fail(
            f"{use.file}:{use.line} calls {use.local}"
            f"{'.' + use.attr if use.attr else ''}"
            f"({use.positional} positional, keywords={list(use.keywords)}) "
            f"but core's signature is {signature}: {exc}"
        )


def test_host_authorization_command_keys_match_core():
    from m8flow_backend import authorization

    assert authorization._PROCESS_START_COMMAND == api.PROCESS_START_COMMAND
    assert authorization._TASK_COMMAND_KEYS == {api.TASK_CLAIM_COMMAND, api.TASK_COMPLETE_COMMAND}
    assert authorization._LIFECYCLE_COMMAND_KEYS == {
        api.PROCESS_SUSPEND_COMMAND,
        api.PROCESS_RESUME_COMMAND,
        api.PROCESS_RETRY_COMMAND,
        api.PROCESS_TERMINATE_COMMAND,
    }
    # HostAuthorizationPolicy matches the import command by literal.
    assert api.PROCESS_DEFINITION_IMPORT_COMMAND == "process_definition.import"


def test_authorization_request_carries_the_fields_the_host_policy_reads():
    fields = {f.name for f in dataclasses.fields(api.AuthorizationRequest)}
    assert {"tenant_id", "actor_user_id", "command_key", "permission", "resource_type", "resource_id"} <= fields


def test_host_policy_implements_core_authorization_protocol():
    from m8flow_backend.authorization import HostAuthorizationPolicy
    from m8flow_backend.workflow import _StartImportPolicy

    core_params = list(inspect.signature(api.AuthorizationPolicy.authorize).parameters)
    for policy in (HostAuthorizationPolicy, _StartImportPolicy):
        assert list(inspect.signature(policy.authorize).parameters) == core_params


@pytest.mark.parametrize(
    "member",
    ["complete", "error", "running", "suspended", "terminated", "user_input_required"],
)
def test_process_instance_status_values_the_host_compares_as_strings(member: str):
    from m8flow_core.models.process_instance import ProcessInstanceStatus

    # The host filters and branches on these raw strings (workflow, task review).
    assert ProcessInstanceStatus[member].value == member
    assert api.ProcessInstanceStatus is ProcessInstanceStatus


def test_tenant_status_active_value_is_stable():
    from m8flow_core.models.tenant import TenantStatus

    # Persisted and filtered on by the scheduler; a renamed value orphans every tenant row.
    assert TenantStatus.ACTIVE.value == "ACTIVE"


@pytest.mark.parametrize(
    "error_cls, status_code, error_code",
    [
        (core_errors.AuthorizationError, 403, "permission_denied"),
        (core_errors.NotFoundError, 404, "not_found"),
        (core_errors.InvalidStateError, 409, "invalid_state"),
        (core_errors.ValidationError, 400, "validation_error"),
        (core_errors.ServiceTaskExecutionError, 500, "service_task_error"),
        (core_errors.BpmnCoreError, 500, "bpmn_core_error"),
    ],
)
def test_core_errors_map_to_host_api_errors(error_cls, status_code, error_code):
    from m8flow_backend.errors import map_bpmn_error

    # Every host command wrapper catches BpmnCoreError; a core error outside
    # that hierarchy would escape as an unmapped 500.
    assert issubclass(error_cls, core_errors.BpmnCoreError)
    mapped = map_bpmn_error(error_cls("boom"))
    assert (mapped.status_code, mapped.error_code, mapped.message) == (status_code, error_code, "boom")


def test_service_task_request_and_context_carry_what_host_wrappers_use():
    from m8flow_core.services.service_tasks import ServiceTaskContext, ServiceTaskRequest

    # Host wrappers rebuild requests with dataclasses.replace(request, parameters=...).
    assert dataclasses.is_dataclass(ServiceTaskRequest)
    request_fields = {f.name for f in dataclasses.fields(ServiceTaskRequest)}
    assert {"operation_id", "parameters", "context"} <= request_fields
    context_fields = {f.name for f in dataclasses.fields(ServiceTaskContext)}
    assert {"tenant_id", "process_instance_id", "task_guid"} <= context_fields


def test_profile_injecting_registry_delegates_every_public_core_registry_method():
    from m8flow_core.services.service_tasks import ServiceTaskRegistry

    from m8flow_backend.connectors.runtime import ProfileInjectingServiceTaskRegistry

    # A core method the wrapper doesn't override would run against the wrapper's
    # own empty registry instead of the inner one, without raising.
    public = {
        name
        for name, member in inspect.getmembers(ServiceTaskRegistry, callable)
        if not name.startswith("_")
    }
    assert public, "core ServiceTaskRegistry exposes no public methods"
    not_delegated = sorted(name for name in public if name not in vars(ProfileInjectingServiceTaskRegistry))
    assert not_delegated == []


def _closure_original(func: Any) -> Any:
    """The unwrapped core callable when the host has already installed its wrapper."""
    nonlocals = inspect.getclosurevars(func).nonlocals
    return nonlocals.get("original", func)


def test_private_connector_proxy_request_hook_keeps_the_shape_proxy_auth_wraps():
    from m8flow_core.services import connector_proxy_service_tasks as mod

    from m8flow_backend.connectors.proxy_auth import _ORIGINAL_ATTR

    original = getattr(mod, _ORIGINAL_ATTR, mod._connector_proxy_json_request)
    params = inspect.signature(original).parameters
    assert {name: p.kind for name, p in params.items()} == {
        name: inspect.Parameter.KEYWORD_ONLY
        for name in ("base_url", "path", "method", "payload", "timeout_seconds", "operation_id")
    }
    # proxy_auth swaps this module global for a subclass that adds the API-key header.
    assert inspect.isclass(mod.Request)
    assert "headers" in inspect.signature(mod.Request).parameters


def test_private_service_task_script_engine_evaluate_keeps_the_shape_the_host_patches():
    from m8flow_core.services.workflow_runtime import _RuntimeServiceTaskScriptEngine

    original = _closure_original(_RuntimeServiceTaskScriptEngine.evaluate)
    params = list(inspect.signature(original).parameters.values())
    assert [p.name for p in params] == ["self", "task", "expression", "external_context"]
    # The host wrapper forwards external_context positionally and defaults it to None.
    assert params[3].default is None
