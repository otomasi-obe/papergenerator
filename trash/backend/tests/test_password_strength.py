"""Password policy tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth_bp.auth import _strong_password


def test_too_short_rejected():
    assert _strong_password("Ab1!") is not None


def test_too_long_rejected():
    assert _strong_password("A" * 200 + "1!") is not None


def test_only_lowercase_rejected():
    assert _strong_password("alllowercase") is not None


def test_three_classes_accepted():
    assert _strong_password("Password1") is None  # upper + lower + digit
    assert _strong_password("password1!") is None  # lower + digit + symbol


def test_two_classes_rejected():
    assert _strong_password("password1") is not None  # only lower + digit
