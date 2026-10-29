# Snyk Debian 13 advisory data correction request

Prepared: 2026-10-26

## Summary

Snyk Container reports four Debian 13 high severity findings for package
versions that Debian's security tracker marks fixed in the forky/sid package
releases. The Snyk findings have no `fixedIn` value, so upgraded images still
show these advisories. A full local image rescan on 2026-10-26 reproduced all
four IDs in fixed images. Please review the package-version ranges and add the
fixed Debian versions to the advisory data.

## Findings

| Snyk ID | Debian CVE | Package in image | Version scanned | Debian fixed version |
| --- | --- | --- | --- | --- |
| `SNYK-DEBIAN13-ACL-17677866` | CVE-2026-54369 | `acl/libacl1` | `2.4.0-1` | `2.4.0-1` |
| `SNYK-DEBIAN13-ATTR-17678182` | CVE-2026-54371 | `attr/libattr1` | `1:2.6.0-1` | `1:2.6.0-1` |
| `SNYK-DEBIAN13-ZLIB-19520500` | CVE-2026-85091 | `zlib/zlib1g` | `1:1.3.dfsg+really1.3.2-4` | `1:1.3.dfsg+really1.3.2-4` |
| `SNYK-DEBIAN13-CYRUSSASL2-20652395` | CVE-2026-107161 | `cyrus-sasl2/libsasl2-2` | `2.1.28+dfsg1-12` | `2.1.28+dfsg1-12` |

The Debian tracker currently lists Trixie as vulnerable and the corresponding
fixed versions in forky/sid. The M8Flow images install these fixed package
versions from Debian sid while retaining their Trixie Python base. This report
does not claim that the versions have been backported to Trixie.

## Reproduction evidence

- Local scan: `snyk container test m8flow-nats-consumer:python-fixed --json`
- The report returned the three Snyk IDs above at the exact package versions
  shown in the table; each finding had an empty `fixedIn` array.
- `dpkg-query -W libacl1 libattr1 zlib1g` inside the image returned:
  - `libacl1 2.4.0-1`
  - `libattr1 1:2.6.0-1`
  - `zlib1g 1:1.3.dfsg+really1.3.2-4`
- A control scan of upstream `python:3.12.15-slim-trixie` still reported the
  same Snyk IDs against older package versions, confirming the reports
  distinguish the package versions.
- Local scans of `m8flow-connector-proxy:highs-fixed` and
  `m8flow-node-wire-proxy:highs-fixed` also reported
  `SNYK-DEBIAN13-CYRUSSASL2-20652395` at `cyrus-sasl2@2.1.28+dfsg1-12` with an
  empty `fixedIn` array. Debian's tracker lists this version as fixed in
  forky/sid.

## Debian references

- CVE-2026-54369: https://security-tracker.debian.org/tracker/CVE-2026-54369
- CVE-2026-54371: https://security-tracker.debian.org/tracker/CVE-2026-54371
- CVE-2026-85091: https://security-tracker.debian.org/tracker/CVE-2026-85091
- CVE-2026-107161: https://security-tracker.debian.org/tracker/CVE-2026-107161

Please update the Debian 13 package version ranges and publish the corresponding
`fixedIn` values, or clarify why these sid-fixed versions remain affected.
