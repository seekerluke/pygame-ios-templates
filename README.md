# pygame-ios-templates

This repository hosts templates fetched by the [pygame-ios](https://github.com/seekerluke/pygame-ios) tool. The Xcode project itself is a modified version of the [empty Briefcase template provided by BeeWare](https://github.com/beeware/briefcase-iOS-Xcode-template). This template also contains pre-built XCFrameworks required by pygame-ce.

## Build Dependencies

To build templates, you need the following dependencies:

- A machine running a recent version of macOS.
- Xcode, you can download this from the App Store.
- Python 3, you can download this from the Python website or through Homebrew.

You can install the required Python packages with `pip install -r requirements.txt`. I recommend using a virtual environment (venv).

From there, you can run `python make_template.py 2.5.6`, replacing the version number with whatever pygame-ce version you want to build a template for. To see all supported versions, see `patches/pygame-ce.json`.

## Making New Templates

I will try to make templates for stable pygame-ce versions as they come out, but if you need a really old version, a fork, or a dev build, then you need to make your own.

To support a new version, you need to do the following:

1. Add a new supported version in `patches/pygame-ce.json`.
2. Clone and checkout the version of pygame-ce you want a template of.
3. Make the necessary changes for iOS (see below).
4. Stage your changes, then create a new patch file with `git diff --cached > pygame-ce_<yourversion>.patch`. The name must match this format exactly.
5. Put your patch file in the `patches` folder, and then run `make_template.py` as described above.

## Conceptual iOS Changes

If you need help with the actual code changes you need, check out the existing patch files in the `patches` folder.

### Meson Cross Files

To cross compile to iOS with Meson, you need:

- `ios-arm64-crossbuild.txt`, used to target actual iPhones and iPads.
- `ios-arm64-simulator-crossbuild.txt`, used to target the iOS Simulator on Macs with Apple Silicon chips (which are arm64).
- `ios-x86_64-simulator-crossbuild.txt`, used to target the iOS Simulator on Macs with Intel chips (which are x86_64).

`make_template.py` runs Meson with these names, so they need to match exactly.

Currently, `make_template.py` does not include steps to build x86_64 modules, because both arm64 and x86_64 simulator builds use the same path in the Xcode project. If you have an Intel Mac, set the `sim_target` variable to use x86_64 instead of arm64. You also need to package x86_64 versions of any binary Python modules you need (eg. numpy) as they are built for arm64 by default.

### Meson Build Files

pygame-ce uses `py.extension_module` for use with meson-python, which cannot cross compile (see [#321](https://github.com/mesonbuild/meson-python/issues/321)). To cross compile with Meson, you need to invoke Meson directly, and therefore need to change all instances of `py.extension_module` to `shared_module`. They are roughly equivalent, the only other change you need to make is changing the `subdir` argument to `install_dir`.

Using Meson directly also means the `py` module doesn't exist, you will get errors. You also won't find a copy of Python installed on the system, because that doesn't make sense on iOS. Instead, use `xcode/Support/Python.xcframework` to set the `py_dep` variable. Also get rid of `pg_dir`.

SDL2 is roughly the same. Use the frameworks under `xcode/Support` to set `sdl_dep` and other variables.

portmidi is not supported, since portmidi itself can't build for iOS. So remove any dependency on portmidi.

Remove `subdir("src_py")`. `make_template.py` will copy the Python scripts into the Xcode project itself.

If the docs are causing issues, remove that from the build files too. You don't need to build the docs to cross compile for iOS.

## Getting New XCFrameworks

pygame-ce's dependencies live in `xcode/Support`. You can replace these XCFrameworks with your own if you wish, if you have specific version requirements. They all have arm64 device binaries, as well as universal simulator binaries (both arm64 and x86_64). You should also replace `SDL2_headers` with headers that match your SDL2 version.
