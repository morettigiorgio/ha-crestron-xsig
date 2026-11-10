# Contributing

Thank you for helping improve Crestron XSIG for Home Assistant. Bug reports,
reproduction details, documentation improvements and focused pull requests are
welcome.

## Before opening an issue

- Check the README, [wiring guide](docs/WIRING.md), and the relevant
  [configuration help](docs/help/README.md).
- Search existing issues to avoid duplicates.
- For a bug, include the Home Assistant version, integration version, install
  method, Crestron processor/model and firmware (if known), steps to reproduce,
  expected behavior, observed behavior, and relevant redacted log excerpts.
- Clearly distinguish a result tested with a real processor from one tested
  only in a simulator or by code inspection.

**Never include credentials, tokens, full Home Assistant backups, private
`crestron.yaml` files, public IP addresses, or unredacted logs/configuration.**
Check serial payloads and entity/device names for personal information before
posting them.

## Development setup

The Home Assistant integration package is in
`custom_components/crestron_xsig/`. It has no Python runtime requirements
outside Home Assistant. For local development, use Python 3.12 or newer and
install the development tools:

```bash
python -m pip install -r requirements-dev.txt
```

Run the same checks used by CI before submitting a pull request:

```bash
python -m ruff check .
python tools/check_flows.py
python tools/test_xsig_hub_protocol.py
```

The GitHub Actions workflow also runs Home Assistant `hassfest` and the HACS
catalog validator used by the built-in Home Assistant Marketplace. Marketplace
(replacing the HACS custom integration from Home Assistant 2026.11) still uses
`hacs.json` and the HACS validation action for catalog checks. The standalone
checks are focused checks, not a substitute for a Home Assistant/Crestron
integration test. If changing a user-facing behavior, record the Home Assistant
and processor versions and the exact test performed.

## Pull requests

- Keep changes focused and explain the problem and the approach.
- Update documentation and translations when changing configuration forms;
  keep `strings.json` and `translations/en.json` in sync.
- Add or update checks for behavior changes. Do not claim hardware validation
  unless it was actually performed.
- Avoid new runtime dependencies unless they are necessary and discussed in
  the pull request.
- Confirm that CI passes and include any remaining limitations or migration
  notes in the pull request description.

Contributions are submitted under the repository's Apache License 2.0. By
submitting a contribution, you confirm that you have the right to submit it
under that license.
