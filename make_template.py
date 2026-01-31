# This script produces a .zip file that can be released on GitHub and fetched by users of pygios.


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
    pygame_dir = os.path.join(SCRIPT_DIR, f"pygame-ce-{version}")

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
        zf.extractall(SCRIPT_DIR)

    print(f"pygame-ce v{version} fetched.")
    return pygame_dir


def apply_patch(pygame_path: str, version: str):
    patch_file_path = os.path.join(SCRIPT_DIR, "patches", f"pygame-ce_{version}.patch")
    with contextlib.chdir(pygame_path):
        result = subprocess.run(
            ["git", "apply", patch_file_path], capture_output=True, text=True
        )

        if result.returncode != 0:
            print("Failed to apply git patch file.")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            raise Exception("Failed to apply git patch file. See previous messages.")

    print("Applied patch file.")


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
        SCRIPT_DIR, "xcode", "pygios", f"app_packages.{type}"
    )
    dest_dir = os.path.join(app_packages_path, "pygame")

    # Remove the app_packages directory if it already exists from previous runs
    if os.path.isdir(app_packages_path):
        shutil.rmtree(app_packages_path)

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
    xcodeproj_path = os.path.join(SCRIPT_DIR, "xcode", "pygios.xcodeproj")
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
    name = f"pygios-template-{version}.zip"

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
