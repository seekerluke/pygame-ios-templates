# This script produces a .zip file that can be released on GitHub and fetched by users of pygame-ios.


import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile

import requests

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "patches", "pygame-ce.json")


def fetch_pygame_release(version: str) -> str:
    build_dir = os.path.join(SCRIPT_DIR, "build")
    os.makedirs(build_dir, exist_ok=True)
    pygame_dir = os.path.join(build_dir, f"pygame-ce-{version}")

    # remove the pygame-ce directory if it still exists from previous runs
    if os.path.isdir(pygame_dir):
        shutil.rmtree(pygame_dir)

    with open(JSON_PATH) as json_file:
        pygame_data = json.load(json_file)
        if version not in pygame_data["supportedVersions"]:
            raise Exception("The specified pygame-ce version is not supported.")

    url = (
        f"https://github.com/pygame-community/pygame-ce/archive/refs/tags/{version}.zip"
    )
    print(f"Downloading pygame-ce v{version}...")
    response = requests.get(url)
    response.raise_for_status()

    print("Extracting...")
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        zf.extractall(build_dir)

    print(f"pygame-ce v{version} fetched.")
    return pygame_dir


def apply_patch(pygame_path: str, version: str):
    patch_file_path = os.path.join(SCRIPT_DIR, "patches", f"pygame-ce_{version}.patch")
    with contextlib.chdir(pygame_path):
        result = subprocess.run(
            ["patch", "-i", patch_file_path], capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"patch command failed: {result.stderr}")

    print("Applied patch file.")

    meson_root_path = os.path.join(pygame_path, "meson.build")
    with open(meson_root_path, "r") as f:
        content = f.read()
    
    # Inject freetype_dep resolution.
    # Use sdl_ttf_framework_inc as anchor — it's unique to the iOS block,
    # avoiding a false match on the emscripten sdl_ttf_dep blocks above it.
    content = content.replace(
        "    sdl_ttf_framework_inc = sdl_ttf_base_path + '/SDL2_ttf.framework/Headers'\n    sdl_ttf_dep = declare_dependency(",
        """    sdl_ttf_framework_inc = sdl_ttf_base_path + '/SDL2_ttf.framework/Headers'
    if ios_arch_slice == 'ios-arm64'
        freetype_base_path = '../freetype_ios'
    else
        freetype_base_path = '../freetype_sim'
    endif
    freetype_dep = declare_dependency(
        include_directories: include_directories(freetype_base_path + '/include/freetype2'),
        link_args: ['-L' + meson.current_source_dir() + '/' + freetype_base_path + '/lib', '-lfreetype'],
        compile_args: ['-I' + meson.current_source_dir() + '/' + freetype_base_path + '/include/freetype2']
    )

    sdl_ttf_dep = declare_dependency("""
    )

    content = content.replace(
        "../xcode/", "../../xcode/"
    )

    with open(meson_root_path, "w") as f:
        f.write(content)

    meson_src_c_path = os.path.join(pygame_path, "src_c", "meson.build")
    with open(meson_src_c_path, "r") as f:
        content_src = f.read()

    # Re-enable _freetype module with shared_module
    content_src = content_src.replace(
        "if portmidi_dep.found()",
        """if freetype_dep.found()
    _freetype = shared_module(
        '_freetype',
        [
            'freetype/ft_cache.c',
            'freetype/ft_wrap.c',
            'freetype/ft_render.c',
            'freetype/ft_render_cb.c',
            'freetype/ft_layout.c',
            'freetype/ft_unicode.c',
            '_freetype.c',
        ],
        c_args: warnings_error + warnings_temp_freetype,
        dependencies: pg_base_deps + freetype_dep,
        install: true,
        install_dir: pg,
    )
endif

if portmidi_dep.found()"""
    )
    
    with open(meson_src_c_path, "w") as f:
        f.write(content_src)

    print("Injected custom FreeType dependencies into meson.build and src_c/meson.build.")


def meson_build(pygame_path: str, target: str):
    with contextlib.chdir(pygame_path):
        subprocess.run(
            [
                "meson",
                "setup",
                f"build-{target}",
                "--cross-file",
                f"{target}-crossbuild.txt",
                "--buildtype=release",
            ]
        )
        subprocess.run(["meson", "compile", "-C", f"build-{target}"])

    print(f'Built binary modules with Meson for target "{target}".')


def move_to_xcode(pygame_path: str, target: str, type: str):
    src_py_path = os.path.join(pygame_path, "src_py")
    native_modules_path = os.path.join(pygame_path, f"build-{target}", "src_c")
    app_packages_path = os.path.join(
        SCRIPT_DIR, "xcode", "pygame-ios", f"app_packages.{type}"
    )
    dest_dir = os.path.join(app_packages_path, "pygame")

    # Remove the app_packages directory if it already exists from previous runs
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)

    shutil.copytree(native_modules_path, dest_dir, dirs_exist_ok=True)

    # rename .dylib files to .so for use in Xcode
    for root, _, files in os.walk(dest_dir):
        for name in files:
            if name.endswith("dylib"):
                new_name = name.replace("dylib", "so").replace("lib", "")
                os.rename(os.path.join(root, name), os.path.join(root, new_name))

    shutil.copytree(src_py_path, dest_dir, dirs_exist_ok=True)

    print(
        f'Copied scripts and binary modules to "app_packages.{type}" in the Xcode project.'
    )


def remove_xcode_metadata():
    xcodeproj_path = os.path.join(SCRIPT_DIR, "xcode", "pygame-ios.xcodeproj")
    xcworkspace_path = os.path.join(xcodeproj_path, "project.xcworkspace")
    xcuserdata_path = os.path.join(xcodeproj_path, "xcuserdata")
    xcshareddata_path = os.path.join(xcodeproj_path, "xcshareddata")

    pbx_template = os.path.join(SCRIPT_DIR, "data", "project.pbxproj")
    pbx_current = os.path.join(xcodeproj_path, "project.pbxproj")

    with contextlib.chdir(xcodeproj_path):
        if os.path.isdir(xcworkspace_path):
            shutil.rmtree(xcworkspace_path)
        if os.path.isdir(xcuserdata_path):
            shutil.rmtree(xcuserdata_path)
        if os.path.isdir(xcshareddata_path):
            shutil.rmtree(xcshareddata_path)

    # fresh copy of project.pbxproj without code signing, provisioning, etc
    shutil.copyfile(pbx_template, pbx_current)

    print("Reset .xcodeproj metadata.")


def finalise(version: str):
    name = f"pygame-ios-template-{version}.zip"

    dist_path = os.path.join(SCRIPT_DIR, "dist")
    result_path = os.path.join(dist_path, name)
    xcode_path = os.path.join(SCRIPT_DIR, "xcode")

    if not os.path.isdir(dist_path):
        os.mkdir(dist_path)

    print(f'Compressing "{xcode_path}"...')
    with zipfile.ZipFile(result_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(xcode_path):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, xcode_path)
                zf.write(full_path, arcname)

    print(f'Done! "{name}" has been created under "{dist_path}".')


if __name__ == "__main__":
    if len(sys.argv) == 2:
        version = sys.argv[1]
        device_target = "ios-arm64"
        sim_target = "ios-arm64-simulator"

        pygame_path = fetch_pygame_release(version)
        apply_patch(pygame_path, version)

        meson_build(pygame_path, device_target)
        meson_build(pygame_path, sim_target)

        move_to_xcode(pygame_path, device_target, "iphoneos")
        move_to_xcode(pygame_path, sim_target, "iphonesimulator")

        remove_xcode_metadata()
        finalise(version)
    else:
        print(f"Usage: {sys.argv[0]} <pygame_version>")
