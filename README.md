# Oriel WebKit

Oriel WebKit packages WPE WebKit and its dependencies for CoreELEC. The
[Oriel framework](https://github.com/GR3ee3N/oriel-framework) uses its
runtime to render web apps inside Kodi.

The Kodi add-on `script.module.oriel.webkit` contains the runtime. A
separate development package supplies headers and libraries for building
against it. CoreELEC provides the system and graphics libraries.

## Status

> [!WARNING]
> **Experimental software.** CoreELEC or Kodi updates can break it.

No support is provided.

## Hardware

Requires an Amlogic device with a Mali GPU running CoreELEC 22
(Kodi 22, 64-bit). Tested on:

- Ugoos AM9 Pro (S905X5M, Mali-G310)
- Ugoos AM6B+ (S922X, Mali-G52)

Other devices and CoreELEC versions have not been tested.

## Installation

For manual installation, download `script.module.oriel.webkit-<version>.zip` from
the [releases page](https://github.com/GR3ee3N/oriel-webkit/releases), then:

1. In Kodi, enable **Settings → System → Add-ons → Unknown sources**.
2. Go to **Add-ons → Install from zip file** and select the downloaded ZIP.

Apps can install this add-on as a dependency through the
[Oriel repository](https://github.com/GR3ee3N/oriel-repository).

## Checks and builds

Use Linux on x86_64 or ARM64 with Docker running. From the repository root:

```sh
tools/check.sh
tools/build.sh
```

`tools/check.sh` runs ShellCheck, Python tests and Buildroot configuration
checks. It does not compile WebKit or remove an existing build. Tests
using the ARM64 compiler also run when a local Buildroot toolchain exists.

`tools/build.sh` compiles and validates the ARM64 runtime using Buildroot
inside Docker. It does not run the test suite. Each build starts with a
fresh build tree; downloaded sources remain cached in `.cache/downloads`.
Set `JOBS` to limit parallel compilation, for example
`JOBS=4 tools/build.sh`.

Output is written to `.cache/runtime`:

- `script.module.oriel.webkit/`: add-on files ready for device deployment.
- `dev/`: development package for compiling against the runtime.
- `buildroot.config`: resolved Buildroot configuration.

`build/versions.env` pins dependency versions. `build/box.env` records the
system and graphics libraries supplied by CoreELEC and the maximum symbol
versions available from its C/C++ runtime. Update this contract when the
target CoreELEC build changes.

## Development package

Download `oriel-webkit-<version>-dev.tar.xz` from the releases page, or use
`.cache/runtime/dev` after a local build. It contains:

- `sysroot/`: headers, pkg-config files and libraries shipped by the add-on.
- `provided.txt`: names of libraries supplied by the add-on.
- `box.env`: CoreELEC library names and supported symbol versions.

## Device testing

After building, deploy to a CoreELEC device over SSH:

```sh
BOX=root@coreelec.local tools/deploy.sh
```

Set `BOX` to the device's SSH address. Deployment requires SSH, rsync and
Kodi's JSON-RPC TCP service. The script waits for add-on registration and
verifies activation on each installation attempt.

Exit and reopen running Oriel apps to load the installed WebKit runtime.

## Releases

Bump `VERSION` in `build/versions.env` and commit. From a clean working tree,
with the GitHub CLI (`gh`) authenticated to publish releases, run:

```sh
tools/release.sh "Release notes"
```

The script exports the committed source, runs checks, builds the runtime
and packages it before uploading a draft release under `v<version>`.
