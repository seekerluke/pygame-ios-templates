#!/bin/bash
set -e

FREETYPE_VERSION="2.13.2"
# Using a reliable mirror for the pre-packaged release tarball that already includes ./configure
FREETYPE_URL="https://mirror.rabisu.com/mirrors/savannah/freetype/freetype-${FREETYPE_VERSION}.tar.gz"

BUILD_DIR="$(pwd)/build"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [ ! -d "freetype-${FREETYPE_VERSION}" ]; then
    echo "Downloading FreeType ${FREETYPE_VERSION}..."
    curl -L -o freetype.tar.gz ${FREETYPE_URL}
    tar -xzf freetype.tar.gz
fi

PREFIX_IOS="${BUILD_DIR}/freetype_ios"
PREFIX_SIM="${BUILD_DIR}/freetype_sim"

mkdir -p $PREFIX_IOS
mkdir -p $PREFIX_SIM

cd freetype-${FREETYPE_VERSION}

# Prevent configure from testing if compiled iOS Simulator binaries execute natively (which hangs CoreSimulator)
sed -i '' 's/cross_compiling=maybe/cross_compiling=yes/g' builds/unix/configure

# Build for ios-arm64
echo "Building for iOS Device (arm64)..."
export CC="$(xcrun -sdk iphoneos -find clang)"
export CXX="$(xcrun -sdk iphoneos -find clang++)"
export AR="$(xcrun -sdk iphoneos -find ar)"
export RANLIB="$(xcrun -sdk iphoneos -find ranlib)"
export CFLAGS="-arch arm64 -isysroot $(xcrun -sdk iphoneos --show-sdk-path) -miphoneos-version-min=13.0 -pipe -O2"
export CXXFLAGS="$CFLAGS"

./configure --prefix="$(pwd)/output_ios" --host=arm64-apple-ios --without-zlib --without-png --without-bzip2 --without-harfbuzz --without-dlg --disable-shared --enable-static
make clean
make -j4
make install

# Build for sim-arm64
echo "Building for iOS Simulator (arm64)..."
export CC="$(xcrun -sdk iphonesimulator -find clang)"
export CXX="$(xcrun -sdk iphonesimulator -find clang++)"
export AR="$(xcrun -sdk iphonesimulator -find ar)"
export RANLIB="$(xcrun -sdk iphonesimulator -find ranlib)"
export CFLAGS="-arch arm64 -isysroot $(xcrun -sdk iphonesimulator --show-sdk-path) -mios-simulator-version-min=13.0 -pipe -O2"
export CXXFLAGS="$CFLAGS"

cross_compiling=yes ./configure --prefix="$(pwd)/output_sim_arm64" --host=arm64-apple-ios --without-zlib --without-png --without-bzip2 --without-harfbuzz --without-dlg --disable-shared --enable-static
make clean
make -j4
make install

# Build for sim-x86_64
echo "Building for iOS Simulator (x86_64)..."
export CFLAGS="-arch x86_64 -isysroot $(xcrun -sdk iphonesimulator --show-sdk-path) -mios-simulator-version-min=13.0 -pipe -O2"
export CXXFLAGS="$CFLAGS"
cross_compiling=yes ./configure --prefix="$(pwd)/output_sim_x86_64" --host=x86_64-apple-ios --without-zlib --without-png --without-bzip2 --without-harfbuzz --without-dlg --disable-shared --enable-static
make clean
make -j4
make install

cd ..

echo "Copying headers and linking fat binaries..."
# Copy headers
cp -r freetype-${FREETYPE_VERSION}/output_ios/include/ $PREFIX_IOS/include
cp -r freetype-${FREETYPE_VERSION}/output_sim_arm64/include/ $PREFIX_SIM/include

mkdir -p $PREFIX_IOS/lib $PREFIX_SIM/lib

# Device library
cp freetype-${FREETYPE_VERSION}/output_ios/lib/libfreetype.a $PREFIX_IOS/lib/libfreetype.a

# Simulator fat library
lipo -create freetype-${FREETYPE_VERSION}/output_sim_arm64/lib/libfreetype.a freetype-${FREETYPE_VERSION}/output_sim_x86_64/lib/libfreetype.a -output $PREFIX_SIM/lib/libfreetype.a

# Create xcframework
echo "Creating FreeType.xcframework..."
XCFRAMEWORK_DIR="$(pwd)/../xcode/Support/freetype.xcframework"
rm -rf "$XCFRAMEWORK_DIR"

xcodebuild -create-xcframework \
    -library "$PREFIX_IOS/lib/libfreetype.a" \
    -headers "$PREFIX_IOS/include" \
    -library "$PREFIX_SIM/lib/libfreetype.a" \
    -headers "$PREFIX_SIM/include" \
    -output "$XCFRAMEWORK_DIR"

echo "Freetype build complete! xcframework created at $XCFRAMEWORK_DIR"
