import hifi_utils
import hifi_android
import hashlib
import os
import platform
import re
import shutil
import tempfile
import json
import xml.etree.ElementTree as ET
import functools
from os import path

print = functools.partial(print, flush=True)

# Encapsulates the vcpkg system
class VcpkgRepo:
    CMAKE_TEMPLATE = """
# this file auto-generated by hifi_vcpkg.py
get_filename_component(CMAKE_TOOLCHAIN_FILE "{}" ABSOLUTE CACHE)
get_filename_component(CMAKE_TOOLCHAIN_FILE_UNCACHED "{}" ABSOLUTE)
set(VCPKG_INSTALL_ROOT "{}")
set(VCPKG_TOOLS_DIR "{}")
"""

    CMAKE_TEMPLATE_NON_ANDROID = """
# If the cached cmake toolchain path is different from the computed one, exit
if(NOT (CMAKE_TOOLCHAIN_FILE_UNCACHED STREQUAL CMAKE_TOOLCHAIN_FILE))
    message(FATAL_ERROR "CMAKE_TOOLCHAIN_FILE has changed, please wipe the build directory and rerun cmake")
endif()
"""

    def __init__(self, args):
        self.args = args
        # our custom ports, relative to the script location
        self.sourcePortsPath = args.ports_path
        self.configFilePath = os.path.join(args.build_root, 'vcpkg.cmake')

        # OS dependent information
        system = platform.system()

        if 'HIFI_VCPKG_PATH' in os.environ:
            self.path = os.environ['HIFI_VCPKG_PATH']
        elif self.args.vcpkg_root is not None:
            self.path = args.vcpkg_root
        else:
            defaultBasePath = os.path.expanduser('~/tivoli/vcpkg')
            basePath = os.getenv('HIFI_VCPKG_BASE', defaultBasePath)

            if self.args.android:
                self.path = os.path.join(basePath, 'android')
            else:
                self.path = os.path.join(basePath, 'desktop')

            if not os.path.isdir(self.path):
                os.makedirs(self.path)

        print("Using vcpkg path {}".format(self.path))
        lockDir, lockName = os.path.split(self.path)
        lockName += '.lock'
        if not os.path.isdir(lockDir):
            os.makedirs(lockDir)

        self.lockFile = os.path.join(lockDir, lockName)
        self.bootstrapEnv = os.environ.copy()
        self.buildEnv = os.environ.copy()

        if 'Windows' == system:
            self.exe = os.path.join(self.path, 'vcpkg.exe')
            self.bootstrapCmds = [
                os.path.join(self.path, 'bootstrap-vcpkg.bat')
            ]
            # self.vcpkgUrl = 'https://cdn.tivolicloud.com/dependencies/vcpkg/vcpkg-win32-client.zip'
            # self.vcpkgHash = 'a650db47a63ccdc9904b68ddd16af74772e7e78170b513ea8de5a3b47d032751a3b73dcc7526d88bcb500753ea3dd9880639ca842bb176e2bddb1710f9a58cd3'
            self.hostTriplet = 'x64-windows'
        elif 'Darwin' == system:
            self.exe = os.path.join(self.path, 'vcpkg')
            self.bootstrapCmds = [os.path.join(self.path, 'bootstrap-vcpkg.sh')]
            self.bootstrapEnv["MACOSX_DEPLOYMENT_TARGET"
                             ] = "10.15"  # just for bootstrapping
            # self.vcpkgUrl = 'https://cdn.tivolicloud.com/dependencies/vcpkg/vcpkg-osx-client.tar'
            # self.vcpkgHash = '519d666d02ef22b87c793f016ca412e70f92e1d55953c8f9bd4ee40f6d9f78c1df01a6ee293907718f3bbf24075cc35492fb216326dfc50712a95858e9cbcb4d'
            self.hostTriplet = 'x64-osx'
        else:
            self.exe = os.path.join(self.path, 'vcpkg')
            self.bootstrapCmds = [os.path.join(self.path, 'bootstrap-vcpkg.sh')]
            self.vcpkgUrl = 'https://cdn.tivolicloud.com/dependencies/vcpkg/vcpkg-linux-client.tar'
            self.vcpkgHash = '6a1ce47ef6621e699a4627e8821ad32528c82fce62a6939d35b205da2d299aaa405b5f392df4a9e5343dd6a296516e341105fbb2dd8b48864781d129d7fba10d'
            self.hostTriplet = 'x64-linux'

        if self.args.android:
            self.triplet = 'arm64-android'
            self.androidPackagePath = os.getenv(
                'HIFI_ANDROID_PRECOMPILED', os.path.join(self.path, 'android')
            )
        else:
            self.triplet = self.hostTriplet

    def writeEnv(self, var, value=""):
        with open(
            os.path.join(self.args.build_root, '_env', var + ".txt"), "w"
        ) as fp:
            fp.write(value)
            fp.close()

    def readEnv(self, var):
        with open(
            os.path.join(self.args.build_root, '_env', var + ".txt")
        ) as fp:
            return fp.read()

    def copyEnvToVcpkg(self):
        print("Passing on variables to vcpkg")
        srcEnv = os.path.join(self.args.build_root, "_env")
        destEnv = os.path.join(self.path, "_env")

        if path.exists(destEnv):
            shutil.rmtree(destEnv)

        shutil.copytree(srcEnv, destEnv)

    # def upToDate(self):
    # 	if self.args.force_build:
    # 		print("Force build, out of date")
    # 		return False
    # 	if not os.path.isfile(self.exe):
    # 		print("Exe file {} not found, out of date".format(self.exe))
    # 		return False
    # 	if not os.path.isfile(self.tagFile):
    # 		print("Tag file {} not found, out of date".format(self.tagFile))
    # 		return False
    # 	with open(self.tagFile, 'r') as f:
    # 		storedTag = f.read()
    # 	if storedTag != self.tagContents:
    # 		print(
    # 			"Tag file {} contents don't match computed tag {}, out of date".
    # 			format(self.tagFile, self.tagContents)
    # 		)
    # 		return False
    # 	return True

    # def clean(self):
    # 	print("Cleaning vcpkg installation at {}".format(self.path))
    # 	if os.path.isdir(self.path):
    # 		print("Removing {}".format(self.path))
    # 		shutil.rmtree(self.path, ignore_errors=True)

    # Make sure the VCPKG prerequisites are all there.
    def bootstrap(self):
        # if self.upToDate():
        # 	return

        downloadVcpkg = False
        if self.args.force_bootstrap:
            print("Forcing bootstrap")
            downloadVcpkg = True

        if not downloadVcpkg and not os.path.isfile(self.exe):
            print("Missing executable, bootstrapping")
            downloadVcpkg = True

        # Make sure we have a vcpkg executable
        testFile = os.path.join(self.path, '.vcpkg-root')
        if not downloadVcpkg and not os.path.isfile(testFile):
            print("Missing {}, bootstrapping".format(testFile))
            downloadVcpkg = True

        bootstrapVcpkg = True
        if (
            platform.system() == "Linux" and
            open("/etc/issue", "r").read().startswith("Debian GNU/Linux 9")
        ):
            bootstrapVcpkg = False

        if downloadVcpkg:
            if bootstrapVcpkg:
                if os.path.isdir(self.path):
                    print("Cloning vcpkg from github to {}".format(self.path))
                    hifi_utils.executeSubprocess(
                        [
                            'git', 'clone',
                            'https://github.com/microsoft/vcpkg.git', self.path
                        ]
                    )
                    print("Bootstrapping vcpkg")
                    hifi_utils.executeSubprocess(
                        self.bootstrapCmds,
                        folder=self.path,
                        env=self.bootstrapEnv
                    )
            else:
                print(
                    "Fetching vcpkg from {} to {}".format(
                        self.vcpkgUrl, self.path
                    )
                )
                hifi_utils.downloadAndExtract(self.vcpkgUrl, self.path)
        else:
            if bootstrapVcpkg:
                print(
                    "Updating vcpkg to latest version at {}".format(self.path)
                )
                hifi_utils.executeSubprocess(['git', 'fetch'], self.path)
                hifi_utils.executeSubprocess(
                    ['git', 'reset', '--hard', 'origin/master'], self.path
                )

        print("Replacing port files")
        portsPath = os.path.join(self.path, 'ports')
        if (os.path.islink(portsPath)):
            os.unlink(portsPath)
        if (os.path.isdir(portsPath)):
            shutil.rmtree(portsPath, ignore_errors=True)
        shutil.copytree(self.sourcePortsPath, portsPath)

    def run(self, commands):
        actualCommands = [self.exe, '--vcpkg-root', self.path]
        actualCommands.extend(commands)
        print(actualCommands)
        hifi_utils.executeSubprocess(
            actualCommands, folder=self.path, env=self.buildEnv
        )

    def setupDependencies(self, qt=None):
        if qt is not None:
            self.buildEnv['QT_CMAKE_PREFIX_PATH'] = qt
            # required for building quazip because cmake in vcpkg port cant read env vars
            self.writeEnv("QT_CMAKE_PREFIX_PATH", qt)

        self.copyEnvToVcpkg()

        # Special case for android, grab a bunch of binaries
        # FIXME remove special casing for android builds eventually
        if self.args.android:
            print("Installing Android binaries")
            self.setupAndroidDependencies()

        # TODO: this is fine but wont downgrade
        print("Installing host tools")
        self.run(['install', '--triplet', self.hostTriplet, 'hifi-host-tools'])

        # If not android, install the hifi-client-deps libraries
        if not self.args.android:
            print("Installing build dependencies")
            self.run(['install', '--triplet', self.triplet, 'hifi-client-deps'])

# def cleanBuilds(self):
#     # Remove temporary build artifacts
#     builddir = os.path.join(self.path, 'buildtrees')
#     if os.path.isdir(builddir):
#     	print("Wiping build trees")
#     	shutil.rmtree(builddir, ignore_errors=True)

    def setupAndroidDependencies(self):
        # vcpkg prebuilt
        if not os.path.isdir(
            os.path.join(self.path, 'installed', 'arm64-android')
        ):
            dest = os.path.join(self.path, 'installed')
            url = "https://cdn.tivolicloud.com/dependencies/vcpkg/vcpkg-arm64-android.tar.gz"
            # FIXME I don't know why the hash check frequently fails here.  If you examine the file later it has the right hash
            #hash = "832f82a4d090046bdec25d313e20f56ead45b54dd06eee3798c5c8cbdd64cce4067692b1c3f26a89afe6ff9917c10e4b601c118bea06d23f8adbfe5c0ec12bc3"
            #hifi_utils.downloadAndExtract(url, dest, hash)
            hifi_utils.downloadAndExtract(url, dest)

        print("Installing additional android archives")
        androidPackages = hifi_android.getPlatformPackages()
        for packageName in androidPackages:
            package = androidPackages[packageName]
            dest = os.path.join(self.androidPackagePath, packageName)
            if os.path.isdir(dest):
                continue
            url = hifi_android.getPackageUrl(package)
            zipFile = package['file'].endswith('.zip')
            print("Android archive {}".format(package['file']))
            hifi_utils.downloadAndExtract(
                url,
                dest,
                isZip=zipFile,
                hash=package['checksum'],
                hasher=hashlib.md5()
            )

    def writeConfig(self):
        print("Writing cmake config to {}".format(self.configFilePath))
        # Write out the configuration for use by CMake
        cmakeScript = os.path.join(
            self.path, 'scripts/buildsystems/vcpkg.cmake'
        )
        installPath = os.path.join(self.path, 'installed', self.triplet)
        toolsPath = os.path.join(
            self.path, 'installed', self.hostTriplet, 'tools'
        )

        cmakeTemplate = VcpkgRepo.CMAKE_TEMPLATE
        if self.args.android:
            precompiled = os.path.realpath(self.androidPackagePath)
            cmakeTemplate += 'set(HIFI_ANDROID_PRECOMPILED "{}")\n'.format(
                precompiled
            )
        else:
            cmakeTemplate += VcpkgRepo.CMAKE_TEMPLATE_NON_ANDROID

        cmakeConfig = cmakeTemplate.format(
            cmakeScript, cmakeScript, installPath, toolsPath
        ).replace('\\', '/')

        with open(self.configFilePath, 'w') as f:
            f.write(cmakeConfig)