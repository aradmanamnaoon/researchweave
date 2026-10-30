# ResearchWeave local AccessKit AT-SPI accessibility fix

This directory contains accesskit_atspi_common version 0.19.1, vendored
from the crates.io source distribution (license: MIT OR Apache-2.0,
upstream: https://github.com/AccessKit/accesskit).

The local patch is restricted to src/node.rs:

- Preserve the ReadOnly state for controls supporting it.
- Expose Enabled and Sensitive only when the underlying AccessKit node
  reports that it is not disabled, regardless of role.

The upstream implementation used is_read_only_supported() as a prerequisite
for omitting Enabled, making disabled Button roles appear enabled to Linux
AT-SPI clients. This must be maintained or removed when a compatible upstream
release resolves the issue, with strict native AT-SPI pagination tests rerun.

The upstream crate's licensing and attribution remain unchanged. Only this
specific adapter is overridden via the root workspace Cargo.toml.
