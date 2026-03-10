import argparse
import os
import re
import shutil
import subprocess
import sys
import json
try:
    import tomllib
except ImportError:
    print("Error: Python 3.11+ is required for tomllib support.", file=sys.stderr)
    sys.exit(1)


def run_cmd(cmd, check=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check)
    return result

def get_or_boot_simulator():
    """Finds a booted iPad simulator or boots the first available one."""
    try:
        output = subprocess.check_output(["xcrun", "simctl", "list", "devices", "-j"])
        data = json.loads(output)

        first_available = None

        for runtime, devices in data.get("devices", {}).items():
            if "iOS" not in runtime:
                continue
            for device in devices:
                if not device.get("isAvailable"):
                    continue

                name = device.get("name", "")
                is_ipad = "iPad" in name or "IPad" in name

                if not is_ipad:
                    continue

                if device.get("state") == "Booted":
                    return name, device.get("udid")

                if first_available is None:
                    first_available = device

        if first_available:
            name = first_available["name"]
            udid = first_available["udid"]
            print(f"No booted iPad simulator found. Booting {name} ({udid})...")
            subprocess.run(["xcrun", "simctl", "boot", udid], check=False)
            subprocess.run(["open", "-a", "Simulator"], check=False)
            return name, udid

    except Exception as e:
        print(f"Error: Failed to auto-detect simulator: {e}", file=sys.stderr)

    print("Error: Could not find any available iOS simulators.", file=sys.stderr)
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Build project for iOS using pygame-ios-template")
    # By default we will clean the old template to ensure a fresh build
    parser.add_argument("--clean", action="store_true", help="Remove existing pygame-ios-template before building", default=False)
    parser.add_argument("--target", choices=["simulator", "ios"], default="simulator", help="Target platform (simulator or ios)")
    parser.add_argument("--config", default="pygame-ios.toml", help="Path to the TOML configuration file")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.getcwd()
    config_path = os.path.join(project_dir, args.config)

    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{args.config}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading configuration from {args.config}...")
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Extract App configuration
    app_config = config.get("app", {})
    APP_NAME = app_config.get("name", "App")
    # Create a safe filename (no spaces or special chars)
    PROJ_NAME = re.sub(r"[^a-zA-Z0-9]", "_", APP_NAME)
    BUNDLE_ID = app_config.get("bundle_id", "com.example.app")
    ICON_PATH = app_config.get("icon_path", "")
    MAIN_MODULE = app_config.get("main_module", "main")

    capabilities_config = config.get("capabilities", {})
    ICLOUD = capabilities_config.get("icloud", False)
    ICLOUD_DOCUMENTS = capabilities_config.get("icloud_documents", False)
    FILES_APP = capabilities_config.get("files_app", False)

    # Extract Build configuration
    build_config = config.get("build", {})
    PYGAME_CE_VERSION = build_config.get("pygame_ce_version", "2.5.6")
    DEVELOPMENT_TEAM = build_config.get("development_team", "")
    SOURCE_DIR = build_config.get("source_dir", ".")
    IGNORE_DIRS = build_config.get("ignore_dirs", [".git", ".venv", "__pycache__", "pygame-ios-template"])
    EXCLUDE_PIP_PACKAGES = build_config.get("exclude_pip_packages", ["pygame-ce", "pygame", "-e"])

    template_dir = os.path.join(project_dir, "pygame-ios-template")

    if args.clean and os.path.exists(template_dir):
        print("Cleaning old template directory...")
        shutil.rmtree(template_dir)

    # 1. Run the pygame-ios template generator
    print("Generating Xcode project using custom local pygame-ios template...")

    # Use the local path relative to the script directory.
    zip_path = os.path.join(script_dir, "dist", f"pygame-ios-template-{PYGAME_CE_VERSION}.zip")
    if not os.path.exists(zip_path):
        print(f"Error: Custom template zip not found at {zip_path}", file=sys.stderr)
        sys.exit(1)

    if args.clean or not os.path.exists(template_dir):
        if os.path.exists(template_dir):
            shutil.rmtree(template_dir)

        os.makedirs(template_dir, exist_ok=True)
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(template_dir)
    else:
        print('Skipping template extraction (use --clean for a fresh start)...')

    app_dir = os.path.join(template_dir, "pygame-ios", "app", "pygame-ios")
    os.makedirs(app_dir, exist_ok=True)

    # Copy all files from SOURCE_DIR to app_dir, ignoring configured directories
    source_path = os.path.join(project_dir, SOURCE_DIR)
    ignore_func = shutil.ignore_patterns(*IGNORE_DIRS)
    for item in os.listdir(source_path):
        if item in IGNORE_DIRS:
            continue
        s = os.path.join(source_path, item)
        d = os.path.join(app_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, ignore=ignore_func, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    if not os.path.exists(template_dir):
        print(f"Error: pygame-ios failed to create the template directory at {template_dir}", file=sys.stderr)
        sys.exit(1)

    # 1.5. Remove the .venv directory that pygame-ios created
    venv_path = os.path.join(template_dir, "pygame-ios", "app", "pygame-ios", ".venv")
    if os.path.exists(venv_path):
        print("Removing macOS .venv directory from Xcode project...")
        shutil.rmtree(venv_path)

    # 2. Patch the Xcode Project File
    # Rename the project file to match the app name
    old_proj_path = os.path.join(template_dir, "pygame-ios.xcodeproj")
    new_proj_path = os.path.join(template_dir, PROJ_NAME + ".xcodeproj")
    if os.path.exists(old_proj_path):
        print(f"Renaming project to {PROJ_NAME}.xcodeproj...")
        os.rename(old_proj_path, new_proj_path)

    pbxproj_path = os.path.join(new_proj_path, "project.pbxproj")
    if os.path.exists(pbxproj_path):
        print(f"Patching bundle identifier in {pbxproj_path}...")
        with open(pbxproj_path, "r", encoding="utf-8") as f:
            pbx_content = f.read()

        pbx_content = pbx_content.replace(
            "PRODUCT_BUNDLE_IDENTIFIER = com.example.pygame-ios;",
            f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};"
        )

        # Patch Product Name
        pbx_content = pbx_content.replace(
            'productName = "pygame-ios";',
            f'productName = "{PROJ_NAME}";'
        )
        pbx_content = pbx_content.replace(
            'productName = pygame-ios;',
            f'productName = "{PROJ_NAME}";'
        )
        pbx_content = pbx_content.replace(
            'PRODUCT_NAME = "pygame-ios";',
            f'PRODUCT_NAME = "{PROJ_NAME}";'
        )
        pbx_content = pbx_content.replace(
            'PRODUCT_NAME = "$(TARGET_NAME)";',
            f'PRODUCT_NAME = "{PROJ_NAME}";'
        )

        # Patch Development Team
        if DEVELOPMENT_TEAM:
            # Use regex to handle both tabs and spaces in the template
            pbx_content = re.sub(r"DEVELOPMENT_TEAM\s*=\s*\"\";", f"DEVELOPMENT_TEAM = {DEVELOPMENT_TEAM};", pbx_content)

            # Map the team ID to the specific pygame-ios target ID
            target_id = "60796EE119190F4100A9926B"
            target_attrs = f"""
\t\t\t\tTargetAttributes = {{
\t\t\t\t\t{target_id} = {{
\t\t\t\t\t\tDevelopmentTeam = {DEVELOPMENT_TEAM};
\t\t\t\t\t}};
\t\t\t\t}};"""

            if "TargetAttributes" not in pbx_content:
                # Replace the line with itself + the new block
                pbx_content = pbx_content.replace(
                    "LastUpgradeCheck = 2620;",
                    f"LastUpgradeCheck = 2620;{target_attrs}"
                )

            # Enable Entitlements if iCloud is used
            if ICLOUD or ICLOUD_DOCUMENTS:
                entitlements_filename = f"{PROJ_NAME}.entitlements"
                entitlements_path = os.path.join(template_dir, "pygame-ios", entitlements_filename)
                print(f"Generating entitlements in {entitlements_path}...")

                entitlements_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.icloud-container-identifiers</key>
    <array>
        <string>iCloud.{BUNDLE_ID}</string>
    </array>
    <key>com.apple.developer.icloud-services</key>
    <array>
        <string>CloudDocuments</string>
    </array>
    <key>com.apple.developer.ubiquity-container-identifiers</key>
    <array>
        <string>iCloud.{BUNDLE_ID}</string>
    </array>
</dict>
</plist>"""
                with open(entitlements_path, "w", encoding="utf-8") as f:
                    f.write(entitlements_content)

                # Tell Xcode to use the entitlements file
                # This search string assumes the template has the default PRODUCT_NAME
                pbx_content = pbx_content.replace(
                    'PRODUCT_NAME = "pygame-ios";',
                    f'PRODUCT_NAME = "pygame-ios";\n\t\t\t\tCODE_SIGN_ENTITLEMENTS = "pygame-ios/{entitlements_filename}";'
                )

        with open(pbxproj_path, "w", encoding="utf-8") as f:
            f.write(pbx_content)

    # 3. Patch the Info.plist Display Name and Main Module
    plist_path = os.path.join(template_dir, "pygame-ios", "pygame-ios-Info.plist")
    if os.path.exists(plist_path):
        print(f"Patching Info.plist in {plist_path}...")
        with open(plist_path, "r", encoding="utf-8") as f:
            plist_content = f.read()

        # Patch Files App Support
        if FILES_APP:
            if "<key>UIFileSharingEnabled</key>" not in plist_content:
                plist_content = plist_content.replace(
                    "</dict>\n</plist>",
                    "\t<key>UIFileSharingEnabled</key>\n\t<true/>\n\t<key>LSSupportsOpeningDocumentsInPlace</key>\n\t<true/>\n</dict>\n</plist>"
                )

        plist_content = plist_content.replace(
            "<key>MainModule</key>\n\t<string>pygame-ios</string>",
            f"<key>MainModule</key>\n\t<string>{MAIN_MODULE}</string>"
        )

        # Update Display Name - try multiple variants to match template
        plist_content = plist_content.replace(
            "<key>CFBundleDisplayName</key>\n\t<string>${PRODUCT_NAME}</string>",
            f"<key>CFBundleDisplayName</key>\n\t<string>{APP_NAME}</string>"
        )
        plist_content = plist_content.replace(
            "<key>CFBundleDisplayName</key>\n\t<string>pygame-ios</string>",
            f"<key>CFBundleDisplayName</key>\n\t<string>{APP_NAME}</string>"
        )
        if "<key>CFBundleDisplayName</key>" not in plist_content:
             plist_content = plist_content.replace(
                "<key>CFBundleName</key>\n\t<string>$(PRODUCT_NAME)</string>",
                f"<key>CFBundleName</key>\n\t<string>$(PRODUCT_NAME)</string>\n\t<key>CFBundleDisplayName</key>\n\t<string>{APP_NAME}</string>"
            )

        if "<key>UIApplicationSupportsIndirectInputEvents</key>" not in plist_content:
            plist_content = plist_content.replace(
                "</dict>\n</plist>",
                "\t<key>UIApplicationSupportsIndirectInputEvents</key>\n\t<true/>\n</dict>\n</plist>"
            )

        with open(plist_path, "w", encoding="utf-8") as f:
            f.write(plist_content)

    # 4. Patch main.m directory change logic
    main_m_path = os.path.join(template_dir, "pygame-ios", "main.m")
    if os.path.exists(main_m_path):
        with open(main_m_path, "r", encoding="utf-8") as f:
            main_m_content = f.read()

        main_m_content = main_m_content.replace(
            "NSString *pygameIosPath = [NSString stringWithFormat:@\"%@/app/%@\", [[NSBundle mainBundle] bundlePath], app_module_name];",
            "NSString *pygameIosPath = [NSString stringWithFormat:@\"%@/app/pygame-ios\", [[NSBundle mainBundle] bundlePath]];"
        )
        main_m_content = main_m_content.replace(
            "path = [NSString stringWithFormat:@\"%@/app\", resourcePath, nil];",
            "path = [NSString stringWithFormat:@\"%@/app/pygame-ios\", resourcePath, nil];"
        )

        with open(main_m_path, "w", encoding="utf-8") as f:
            f.write(main_m_content)

    # 4.5. Set App Icon
    if ICON_PATH:
        print("Setting app icon...")
        icon_source = os.path.join(project_dir, ICON_PATH)
        icon_dest_dir = os.path.join(template_dir, "pygame-ios", "Images.xcassets", "AppIcon.appiconset")
        if os.path.exists(icon_source) and os.path.exists(icon_dest_dir):
            # Clean out existing icons to prevent 'unassigned child' warnings
            for f in os.listdir(icon_dest_dir):
                if f.endswith(".png"):
                    os.remove(os.path.join(icon_dest_dir, f))

            icon_dest_path = os.path.join(icon_dest_dir, "custom_icon.png")
            shutil.copy2(icon_source, icon_dest_path)

            # Upscale to 1024x1024 to satisfy actool validation
            run_cmd(["sips", "-z", "1024", "1024", icon_dest_path])

            contents_json_path = os.path.join(icon_dest_dir, "Contents.json")
            with open(contents_json_path, "r") as f:
                contents = json.load(f)

            contents["images"] = [
                {
                    "filename": "custom_icon.png",
                    "idiom": "universal",
                    "platform": "ios",
                    "size": "1024x1024"
                }
            ]

            with open(contents_json_path, "w") as f:
                json.dump(contents, f, indent=2)
        else:
            print(f"Warning: Could not find icon source {icon_source} or destination {icon_dest_dir}")

    # Only install requirements if we are cleaning or if they are missing
    app_pkg_check = os.path.join(template_dir, "pygame-ios", "app_packages.iphoneos")
    if args.clean or not os.path.exists(app_pkg_check):
        print("Exporting pip requirements...")
        requirements_path = os.path.join(project_dir, "requirements-ios.txt")

        # Generate requirements-ios.txt using uv
        run_cmd(["uv", "export", "--format", "requirements-txt", "--output-file", requirements_path])

        print("Filtering out incompatible C-extensions...")
        with open(requirements_path, "r", encoding="utf-8") as f:
            req_lines = f.readlines()

        with open(requirements_path, "w", encoding="utf-8") as f:
            for line in req_lines:
                pkg_name = line.split("==")[0].split()[0].strip().lower() if line.strip() and not line.startswith("#") else ""
                if pkg_name not in EXCLUDE_PIP_PACKAGES:
                    f.write(line)

        print("Installing requirements into app_packages.iphonesimulator and app_packages.iphoneos...")

        for platform in ["app_packages.iphonesimulator", "app_packages.iphoneos"]:
            app_packages_dir = os.path.join(template_dir, "pygame-ios", platform)
            os.makedirs(app_packages_dir, exist_ok=True)
            run_cmd([
                sys.executable, "-m", "pip", "install",
                "--target", app_packages_dir,
                "--no-deps",
                "-r", requirements_path
            ])

        if os.path.exists(requirements_path):
            os.remove(requirements_path)
    else:
        print('Skipping pip installation (use --clean to update requirements)...')

    # 5. Build
    print(f"Building for {args.target}...")
    if args.target == "simulator":
        sim_name, sim_udid = get_or_boot_simulator()
        destination = f"platform=iOS Simulator,id={sim_udid}"
    else:
        destination = "generic/platform=iOS"

    xcodebuild_cmd = [
        "xcodebuild", "-project", os.path.join(template_dir, PROJ_NAME + ".xcodeproj"),
        "-scheme", "pygame-ios",
        "-destination", destination,
        "build",
        "-derivedDataPath", os.path.join(template_dir, "build"),
        "-allowProvisioningUpdates"
    ]

    if DEVELOPMENT_TEAM:
        xcodebuild_cmd.append(f"DEVELOPMENT_TEAM={DEVELOPMENT_TEAM}")

    run_cmd(xcodebuild_cmd)

    if args.target == "simulator":
        print(f"Installing on Simulator ({sim_name})...")
        run_cmd([
            "xcrun", "simctl", "install", sim_udid,
            os.path.join(template_dir, "build", "Build", "Products", "Debug-iphonesimulator", f"{PROJ_NAME}.app")
        ])

        print(f"Launching on Simulator ({sim_name})...")
        run_cmd([
            "xcrun", "simctl", "launch", sim_udid, BUNDLE_ID
        ])
        print("\n--- Build and Launch Complete! ---")
    else:
        print("\n--- Build Complete! ---")
        print("To run on a physical device, open the project in Xcode and deploy to your device.")


if __name__ == "__main__":
    main()