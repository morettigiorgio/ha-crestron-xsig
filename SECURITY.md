# Security policy

Crestron XSIG is a local Home Assistant integration that accepts a TCP
connection from a Crestron processor. Please report suspected vulnerabilities
privately; do not publish exploit details, credentials, packet captures, or
sensitive configuration in a public issue.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** feature in the repository's Security
tab (Private vulnerability reporting / Security Advisories). If that option is
not available, contact the maintainer privately through the
[GitHub profile](https://github.com/morettigiorgio). Do not open a public issue
for an unpatched security vulnerability.

Include, where possible:

- affected integration version and Home Assistant version;
- a concise description and reproducible impact;
- the minimum information needed to reproduce the issue.

Redact credentials, tokens, real IP addresses, join values that disclose a
private installation, personal entity names, and unrelated Home Assistant or
Crestron configuration. Do not attach a full backup or an unredacted log.

## Response and disclosure

The maintainer will acknowledge and investigate reports as time permits; no
fixed response or remediation time is guaranteed. Please allow time for
investigation and a coordinated fix before public disclosure. The maintainer
will coordinate any public advisory with the reporter when possible.

## Supported versions

Security fixes are intended for the latest published version. Older versions
may not receive backports; upgrade to the latest release before reporting that
an issue remains reproducible.
