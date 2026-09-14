# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries below 0.4.0 were reconstructed from the commit history after the fact.

## [Unreleased]

## [0.3.0] - 2026-09-07

### Changed

- The runtime image is built on a distroless base. pip is no longer part of the
  shipped image, and the interpreter moved from Python 3.14 to 3.13. The image
  shrank from roughly 140 MB to 74 MB.
- Base image digest updates from Renovate.

### Added

- Trivy vulnerability scan in the image pipeline. Findings are printed to the job
  log and uploaded to the GitHub Security tab; they do not fail the build.

### Security

- Dropping pip from the image resolved two HIGH advisories that came from pip's
  vendored dependencies: msgpack 1.1.2 (GHSA-6v7p-g79w-8964) and setuptools
  70.3.0 (CVE-2025-47273). Neither was used at runtime.

## [0.2.0] - 2026-08-23

Version bump only. The content is identical to 0.1.2.

## [0.1.2] - 2026-08-23

### Added

- Diagnostic telemetry from msmart-ng in the state payload: compressor
  frequency, current and voltage, indoor and outdoor coil temperatures,
  discharge pipe temperature, target and actual indoor fan speed, water pump
  state, outdoor unit power, and horizontal and vertical louver angles. The
  bridge enables the corresponding msmart-ng data request groups.

### Fixed

- Discovery no longer requires a token and key pair.
- Discovery output includes the discovered port.
- Discovery output is flushed before exit, so nothing is lost in one-shot runs.

### Changed

- msmart-ng updated to 2026.8.0.
- `actions/setup-python` updated to v7, base image digests updated.

## [0.1.1] - 2026-07-04

### Added

- One-shot discovery workflow with `docker-compose.discovery.yml`.
- Flash and fresh air controls exposed over MQTT: `flash`, `supports_flash`,
  `fresh_air_fan_speed` and `supports_fresh_air`. `flash_cool` remains available
  as a compatibility alias for the upstream rename of Jet Cool to Flash.

### Fixed

- Eco and turbo use the public msmart-ng attributes.
- No fallback to private flash commands.

### Changed

- Version tags are published only when `VERSION` actually changes.
- The compose example uses the published GHCR image.
- msmart-ng updated to 2026.7.0, python base image pinned by digest.

## [0.1.0] - 2026-07-01

### Added

- Standalone Midea and PortaSplit MQTT bridge, usable with any MQTT consumer,
  including FHEM MQTT2 examples.
- Discovery override for a one-shot device lookup.
- Docker image pipeline publishing multi-arch images for `linux/amd64` and
  `linux/arm64` to GHCR, with `VERSION` as the single source of the version.
