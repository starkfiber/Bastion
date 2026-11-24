"""Explicit optional native-test dependency, never a guessed plugin version."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re


class NativeFixtureError(ValueError):
    pass


@dataclass(frozen=True)
class NativeFixture:
    path: Path
    sha256: str


def resolve_native_fixture(environ=None):
    env = os.environ if environ is None else environ
    path_value = env.get("BASTION_TEST_NATIVE_ENGINE")
    pin = env.get("BASTION_TEST_NATIVE_SHA256")
    if path_value is None and pin is None:
        return None
    if not isinstance(path_value, str) or not path_value or not isinstance(pin, str) or not pin:
        raise NativeFixtureError("configure both BASTION_TEST_NATIVE_ENGINE and BASTION_TEST_NATIVE_SHA256")
    if not re.fullmatch(r"[a-f0-9]{64}", pin):
        raise NativeFixtureError("native fixture SHA-256 must be 64 lowercase hexadecimal characters")
    path = Path(path_value).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise NativeFixtureError("configured native fixture must be an absolute regular non-symlink file")
    if not os.access(path, os.X_OK):
        raise NativeFixtureError("configured native fixture is not executable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
        raise NativeFixtureError("configured native fixture hash mismatch")
    return NativeFixture(path, pin)


def require_native_fixture(environ=None):
    value = resolve_native_fixture(environ)
    if value is None:
        raise NativeFixtureError("native qualification requires BASTION_TEST_NATIVE_ENGINE and BASTION_TEST_NATIVE_SHA256")
    return value
