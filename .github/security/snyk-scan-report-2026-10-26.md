# Local Snyk container scan report

**Scan date:** 2026-10-26  
**Scanner:** Local Snyk CLI (`1.1308.1`)  
**Scope:** 32 images across the workflow image matrix, M8Flow application images, and Python development targets.  
**Result:** 0 critical findings; 139 high finding occurrences across 10 images. Occurrences include repeated dependency paths and are not unique vulnerabilities.

This report preserves the results recorded from the local scan. The original temporary Snyk JSON files were removed after the scan, so this Markdown file is a findings summary rather than a raw Snyk export. The local Docker daemon was inaccessible during report preparation, so the scan was not rerun.

## High findings

| Snyk advisory | Package | Versions reported | Notes |
|---|---|---|---|
| `SNYK-DEBIAN13-ACL-17677866` | ACL (`libacl1`) | `2.3.2-2+b1`, `2.4.0-1` | The updated version is still reported because Snyk lists no `fixedIn` version. |
| `SNYK-DEBIAN13-ATTR-17678182` | Attr (`libattr1`) | `1:2.5.2-3`, `1:2.6.0-1` | The updated version is still reported because Snyk lists no `fixedIn` version. |
| `SNYK-DEBIAN13-ZLIB-19520500` | zlib (`zlib1g`) | `1:1.3.dfsg+really1.3.1-1+b1`, `1:1.3.dfsg+really1.3.2-4` | The updated version is still reported because Snyk lists no `fixedIn` version. |
| `SNYK-DEBIAN13-CYRUSSASL2-20652395` | Cyrus SASL | `2.1.28+dfsg1-12` | Reported in connector proxy and Node wire proxy images; Snyk lists no `fixedIn` version. |

## Images with high findings

The ACL, attr, and zlib advisories appeared in these 10 scan targets:

- `m8flow-connector-proxy-dev-python-fixed`
- `m8flow-connector-proxy`
- `m8flow-mcp`
- `m8flow-nats-consumer-python-fixed`
- `m8flow-node-24.22.1-trixie-slim`
- `m8flow-node-wire-proxy`
- `m8flow-python-3.12-slim-trixie`
- `m8flow-python-3.12.15-slim-trixie`
- `node-24.22.1-trixie-slim-upstream`
- `python-3.12.15-slim-trixie-upstream`

The Cyrus SASL advisory also appeared in `m8flow-connector-proxy-dev-python-fixed`, `m8flow-connector-proxy`, and `m8flow-node-wire-proxy`.

## Other scan notes

- No critical findings were recorded across the 32 scanned images.
- The refreshed Keycloak scan no longer reported the previously observed high finding. Its reported JDK package version was unchanged, so this result does not establish that a vendor package update fixed the issue.
- The custom Loki image build failed locally. Its result is unconfirmed; the upstream Loki fallback scan was clear at high and critical severity.
- Upstream Python and Node images remain in the scan matrix as comparison baselines and report older versions of the Debian packages above.

## Debian advisory references

- [ACL / CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369)
- [Attr / CVE-2026-54371](https://security-tracker.debian.org/tracker/CVE-2026-54371)
- [zlib / CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091)
- [Cyrus SASL / CVE-2026-107161](https://security-tracker.debian.org/tracker/CVE-2026-107161)

See [the Snyk advisory data correction evidence](snyk-debian13-advisory-data-correction.md) for the package version comparison and supporting details.
