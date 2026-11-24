# Configure the optional native test fixture

The test suite does not guess a plugin version or search another user's directories. Select a reviewed native executable explicitly and supply its expected SHA-256 from your reviewed artifact identity:

```sh
export BASTION_TEST_NATIVE_ENGINE="/absolute/path/to/reviewed/rf2-harness"
export BASTION_TEST_NATIVE_SHA256="REVIEWED_64_CHARACTER_LOWERCASE_SHA256"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Replace both placeholders before running. The executable must be an absolute, regular, executable file, not a symlink. The hash must match its exact bytes. The fixture validates configuration without executing the file; the native test cases then exercise its checked-sum and decision contract. A matching hash is an identity pin, not a signature or permission to execute unreviewed code.

| Configuration | Result |
| --- | --- |
| Neither variable supplied | The three optional native tests explicitly skip; ordinary tests still run |
| Only one supplied, empty values or malformed hash | Test discovery fails with a configuration error |
| Explicit missing, relative, symlink or non-executable file | Test discovery fails; it does not silently skip |
| Wrong expected hash | Test discovery fails before running the native tests |
| Valid reviewed executable and exact expected hash | All three original native cases execute with that dependency |

The fixture-discovery tests include a subprocess control proving that explicitly missing or incorrectly pinned dependencies cause the native-test CLI to fail. They do not disable existing assertions or turn skipped tests into passes. The review adds ten discovery controls to the original 97-case suite, for 107 cases total.

The configured review run passed all 107 cases with zero skips; the three native cases appeared as executed successes. This is a local test observation, not a portable-platform or release-installation claim. See [validation scope](VALIDATION.md).

The native-backed qualification helpers `tools/qualify_checks.py` and `tools/qualify_mixed_missions.py` use the same two variables and require them. They do not choose an old installed plugin automatically. Preserve their previous evidence and review their actual workload before intentionally executing them.

## Repository QA recipe

The bundled recipe includes the fixture helper and its tests in the exact source allowlist and expects 107 observed cases. Keep the two variables set when you require native coverage. A report that contains optional skips must identify them; an overall successful unittest exit is not proof those skipped cases executed.

Native-backed execution remains macOS ARM64-qualified only. Python executes the Python tests; RF² supplies the configured bounded calculations and decision gates. This fixture configuration does not install a plugin, change a project's native settings, migrate a journal or grant new execution authority.
