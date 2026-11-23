# 0.6 candidate publication preparation

This local 0.6 candidate is prepared for the owner-authorized public repository https://github.com/starkfiber/Bastion under the MIT License. Preparing the package does not itself publish it. No separate website or GitHub Pages deployment is configured.

The bundle includes original source, tests, demo inputs, documentation, generated illustration, exact diagram, sanitized CLI capture, measured timing samples and a manually triggered CI definition. It excludes Git history, runtime journals, SQLite databases, temporary evidence workspaces, absolute-path-rich qualification reports, copied research repositories and installed native binaries.

The curated source normalizes hardcoded optional engine paths in test/qualification helpers to Path.home(). Runtime code is copied unchanged from this candidate worktree. The new QA workflow is prepared locally, not dispatched remotely. A file-hash manifest records the exact prepared contents. Link and credential-pattern checks are bounded heuristics, not a guarantee that publication has no risk. The owner selected public visibility and the MIT License for starkfiber/Bastion. Future publication to other destinations still requires owner authorization.

The original CI file uses official actions/checkout@v7 and actions/setup-python@v7 examples, contents:read permissions, and workflow_dispatch only. It has not run on GitHub. Reference documentation: https://github.com/actions/checkout and https://github.com/actions/setup-python .

The additional repository-task workflow retains only named reports through actions/upload-artifact@v7, with seven-day retention. Its syntax was checked against https://github.com/actions/upload-artifact . Neither hosted workflow has been run as part of Task Edition qualification.
