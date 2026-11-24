"""Native discovery controls: absent is optional, explicit bad configuration fails."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.native_fixture import NativeFixtureError, require_native_fixture, resolve_native_fixture


class NativeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bastion-native-discovery-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic executable"
        self.path.write_bytes(b"reviewed synthetic discovery bytes; never executed")
        self.path.chmod(0o700)
        self.pin = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.env = {"BASTION_TEST_NATIVE_ENGINE": str(self.path), "BASTION_TEST_NATIVE_SHA256": self.pin}

    def test_absent_optional_fixture_and_required_qualification(self):
        self.assertIsNone(resolve_native_fixture({}))
        with self.assertRaisesRegex(NativeFixtureError, "requires"):
            require_native_fixture({})

    def test_configuration_requires_both_fields(self):
        for key in self.env:
            with self.subTest(key=key), self.assertRaisesRegex(NativeFixtureError, "configure both"):
                resolve_native_fixture({key: self.env[key]})

    def test_valid_explicit_fixture_preserves_reviewed_path_and_pin(self):
        value = resolve_native_fixture(self.env)
        self.assertEqual(value.path, self.path)
        self.assertEqual(value.sha256, self.pin)

    def test_explicit_missing_path_is_an_error(self):
        self.path.unlink()
        with self.assertRaisesRegex(NativeFixtureError, "absolute regular"):
            resolve_native_fixture(self.env)

    def test_wrong_pin_is_an_error(self):
        with self.assertRaisesRegex(NativeFixtureError, "hash mismatch"):
            resolve_native_fixture(dict(self.env, BASTION_TEST_NATIVE_SHA256="0" * 64))

    def test_malformed_pin_is_an_error(self):
        for pin in ("", "0" * 63, "A" * 64):
            with self.subTest(pin=pin), self.assertRaises(NativeFixtureError):
                resolve_native_fixture(dict(self.env, BASTION_TEST_NATIVE_SHA256=pin))

    def test_relative_path_is_an_error(self):
        with self.assertRaisesRegex(NativeFixtureError, "absolute regular"):
            resolve_native_fixture(dict(self.env, BASTION_TEST_NATIVE_ENGINE="relative/engine"))

    def test_symlink_is_an_error(self):
        link = self.path.parent / "alias";link.symlink_to(self.path)
        with self.assertRaisesRegex(NativeFixtureError, "non-symlink"):
            resolve_native_fixture(dict(self.env, BASTION_TEST_NATIVE_ENGINE=str(link)))

    def test_nonexecutable_fixture_is_an_error(self):
        self.path.chmod(0o600)
        with self.assertRaisesRegex(NativeFixtureError, "not executable"):
            resolve_native_fixture(self.env)

    def test_explicit_bad_configuration_fails_native_test_cli_instead_of_skipping(self):
        for value in (dict(self.env, BASTION_TEST_NATIVE_SHA256="0" * 64),
                      dict(self.env, BASTION_TEST_NATIVE_ENGINE=str(self.path.parent / "missing"))):
            env = dict(os.environ, **value, PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_missions.NativeTests", "-v"],
                                    cwd=Path(__file__).resolve().parents[1], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("NativeFixtureError", result.stderr)
            self.assertNotIn("skipped", result.stderr)
