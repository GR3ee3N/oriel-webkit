# Oriel WebKit

Oriel WebKit packages WPE WebKit and its dependencies for CoreELEC. It provides
the runtime and development libraries used by the
[Oriel framework](https://github.com/GR3ee3N/oriel-framework).

The runtime is distributed as the Kodi add-on `script.module.oriel.webkit`.
A separate development package contains the headers and libraries needed to
build against it. CoreELEC supplies the system and graphics libraries.

## Status

> [!WARNING]
> **Oriel WebKit is highly experimental.** It is a personal project, tested on only
> a few boxes, and it relies on CoreELEC and Kodi internals that are outside its control.
> Any update to those can break it, and it could stop working at any time.
> Use it at your own risk.

No support is provided.

## Hardware

The runtime targets Amlogic devices with a Mali GPU running CoreELEC 22
(Kodi 22, 64-bit). It has been tested on:

- Ugoos AM9 Pro (S905X5M)
- Ugoos AM6B+ (S922X)

Other devices and CoreELEC versions have not been tested.

## Installation

Download `script.module.oriel.webkit-<version>.zip` from the
[releases page](https://github.com/GR3ee3N/oriel-webkit/releases).

1. In Kodi, enable **Settings → System → Add-ons → Unknown sources**.
2. Go to **Add-ons → Install from zip file** and select the downloaded ZIP.

Apps can also install the runtime as a dependency through the
[Oriel repository](https://github.com/GR3ee3N/oriel-repository).

## Building

Building requires Linux on x86_64 or ARM64 and a running Docker installation.
Run these commands from the repository root:

```sh
tools/check.sh
tools/build.sh
```

`tools/check.sh` runs ShellCheck, the Python tests and Buildroot configuration
checks without compiling WebKit or removing an existing build. ARM64 compiler
tests also run when a local Buildroot toolchain is available. `tools/build.sh`
builds and validates the runtime; it does not run the test suite.

The build uses Buildroot inside Docker to compile the ARM64 toolchain, WebKit
and its dependencies. Each run starts from a clean build tree; downloaded
sources are cached in `.cache/downloads`. Set `JOBS` to limit parallel jobs,
for example `JOBS=4 tools/build.sh`.

Build output is written to `.cache/runtime`:

- `script.module.oriel.webkit/` — the add-on, ready to deploy to a device.
- `dev/` — the development package used to build against the runtime.
- `buildroot.config` — the resolved Buildroot configuration.

Dependency versions are pinned in `build/versions.env`. `build/box.env`
records the system and graphics libraries supplied by CoreELEC and the newest
symbol versions available in its C and C++ runtime. Update it when the target
CoreELEC build changes.

## Development package

The development package is available as `oriel-webkit-<version>-dev.tar.xz`
on the releases page, or in `.cache/runtime/dev` after a local build. It contains:

- `sysroot/` — headers, pkg-config files and the libraries shipped by the add-on.
- `provided.txt` — the list of libraries supplied by the add-on.
- `box.env` — the CoreELEC system library list and available symbol versions.

## Testing on a device

After building, deploy the add-on to a CoreELEC device over SSH:

```sh
BOX=root@coreelec.local tools/deploy.sh
```

Replace `root@coreelec.local` with the device's SSH address. Deployment requires
SSH, rsync and Kodi's JSON-RPC TCP service. The script waits for Kodi to
register the add-on and verifies activation on every install, including retries.
Reopen running Oriel apps to load the updated runtime.

## Releasing

Bump `VERSION` in `build/versions.env` and commit the change. Build and publish
from a clean working tree using the GitHub CLI (`gh`), authenticated with an
account that can publish releases:

```sh
tools/release.sh "Release notes"
```

`tools/release.sh` exports the committed source, runs checks, builds the runtime
and packages it before uploading a draft under `v<version>`.
