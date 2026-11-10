# Known issues and verification gaps

This list covers limitations that affect users or still need verification;
it is not a history of completed development tasks. See
[TESTING.md](TESTING.md) for the evidence currently available.

## Not yet verified

- **Crestron synchronization after legacy import:** the legacy YAML import
  flow has been manually tested successfully in Home Assistant, but a successful
  live synchronization of the imported rules with a Crestron processor has not
  yet been reported. Verify the imported joins against your processor.

Report reproducible problems through the project's GitHub issue tracker.
Avoid including credentials or private configuration data.
