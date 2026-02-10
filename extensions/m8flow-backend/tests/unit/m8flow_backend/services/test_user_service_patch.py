"""Unit tests for user_service_patch: lock return contract of add_user_to_group_or_add_to_waiting.

The patched method is called by authorization_service (spiffworkflow_backend) which expects
a 2-tuple (wugam, user_to_group_identifiers). These tests ensure the contract is preserved.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from m8flow_backend.services import user_service_patch


def _apply_patch() -> None:
    user_service_patch._PATCHED = False
    user_service_patch.apply()


def test_add_user_to_group_or_add_to_waiting_returns_two_tuple() -> None:
    """Patched method always returns a 2-tuple (first element may be None or wugam, second is list of dicts)."""
    from spiffworkflow_backend.services.user_service import UserService

    mock_user_model = MagicMock()
    mock_user_model.query.filter.return_value.all.return_value = []

    with patch("spiffworkflow_backend.models.user.UserModel", mock_user_model):
        _apply_patch()
        with patch.object(UserService, "add_waiting_group_assignment") as mock_waiting:
            mock_waiting.return_value = (MagicMock(), [{"username": "u", "group_identifier": "g"}])
            result = UserService.add_user_to_group_or_add_to_waiting("nobody", "group-id")

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_add_user_to_group_or_add_to_waiting_no_users_returns_waiting_result() -> None:
    """When no users match, the result equals add_waiting_group_assignment return (same type/structure)."""
    from spiffworkflow_backend.services.user_service import UserService

    fake_wugam = MagicMock()
    waiting_identifiers = [{"username": "pending", "group_identifier": "grp"}]
    mock_user_model = MagicMock()
    mock_user_model.query.filter.return_value.all.return_value = []

    with patch("spiffworkflow_backend.models.user.UserModel", mock_user_model):
        _apply_patch()
        with patch.object(UserService, "add_waiting_group_assignment") as mock_waiting:
            mock_waiting.return_value = (fake_wugam, waiting_identifiers)
            result = UserService.add_user_to_group_or_add_to_waiting("nobody", "grp")

    assert result[0] is fake_wugam
    assert result[1] == waiting_identifiers
    mock_waiting.assert_called_once()


def test_add_user_to_group_or_add_to_waiting_users_found_returns_none_and_list() -> None:
    """When users are found, first element is None and second is list of dicts with username and group_identifier."""
    from spiffworkflow_backend.services.user_service import UserService

    mock_user1 = MagicMock()
    mock_user1.username = "alice"
    mock_user2 = MagicMock()
    mock_user2.username = "bob"
    mock_group = MagicMock()
    mock_group.identifier = "test-group"
    mock_user_model = MagicMock()
    mock_user_model.query.filter.return_value.all.return_value = [mock_user1, mock_user2]

    with patch("spiffworkflow_backend.models.user.UserModel", mock_user_model):
        _apply_patch()
        with (
            patch.object(UserService, "find_or_create_group", return_value=mock_group),
            patch.object(UserService, "add_user_to_group"),
        ):
            result = UserService.add_user_to_group_or_add_to_waiting("alice@realm", "test-group")

    assert result[0] is None
    assert isinstance(result[1], list)
    assert len(result[1]) == 2
    for item in result[1]:
        assert "username" in item
        assert "group_identifier" in item
        assert item["group_identifier"] == "test-group"
    usernames = {item["username"] for item in result[1]}
    assert usernames == {"alice", "bob"}
