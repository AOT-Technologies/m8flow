# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Pytest defaults for m8flow-node-wire-proxy."""

from __future__ import annotations

import os

# Allow importing/creating the app without a shared secret in unit tests.
# Auth enforcement is covered explicitly in test_auth.py.
os.environ.setdefault("NW_ALLOW_UNAUTHENTICATED", "1")
