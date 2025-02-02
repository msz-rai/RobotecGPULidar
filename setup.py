#!/usr/bin/env python3
import os
import platform
import sys
import re
import subprocess
import shutil
import argparse


class Config:
    # Default values for Linux
    CUDA_MIN_VER_MAJOR = 11
    CUDA_MIN_VER_MINOR = 7
    CUDA_MIN_VER_PATCH = 0
    CMAKE_GENERATOR = "'Unix Makefiles'"
    VCPKG_INSTALL_DIR = os.path.join("external", "vcpkg")
    VCPKG_TAG = "2023.08.09"
    VCPKG_EXEC = "vcpkg"
    VCPKG_BOOTSTRAP = "bootstrap-vcpkg.sh"
    VCPKG_TRIPLET = "x64-linux"

    def __init__(self):
        # Platform-dependent configuration
        if inside_docker():
            self.VCPKG_INSTALL_DIR = os.path.join("/rgldep", "vcpkg")

        if on_windows():
            self.CUDA_MIN_VER_MINOR = 4
            self.CUDA_MIN_VER_PATCH = 152  # patch for CUDA 11.4 Update 4
            self.CMAKE_GENERATOR = "Ninja"
            self.VCPKG_EXEC = "vcpkg.exe"
            self.VCPKG_BOOTSTRAP = "bootstrap-vcpkg.bat"
            self.VCPKG_TRIPLET = "x64-windows"


def main():
    cfg = Config()
    # Parse arguments
    parser = argparse.ArgumentParser(description="Helper script to build RGL.")
    parser.add_argument("--build-dir", type=str, default="build",
                        help="Path to build directory. Default: 'build'")
    parser.add_argument("--install-pcl-deps", action='store_true',
                        help="Install dependencies for PCL extension and exit")
    parser.add_argument("--clean-build", action='store_true',
                        help="Remove build directory before cmake")
    parser.add_argument("--with-pcl", action='store_true',
                        help="Build RGL with PCL extension")
    parser.add_argument("--with-ros2", action='store_true',
                        help="Build RGL with ROS2 extension")
    parser.add_argument("--with-ros2-standalone", action='store_true',
                        help="Build RGL with ROS2 extension and install all dependent ROS2 libraries additionally")
    parser.add_argument("--with-udp", action='store_true',
                        help="Build RGL with UDP extension (closed-source extension)")
    parser.add_argument("--cmake", type=str, default="",
                        help="Pass arguments to cmake. Usage: --cmake=\"args...\"")
    if on_linux():
        parser.add_argument("--make", type=str, default=f"-j{os.cpu_count()}", dest="build_args",
                            help="Pass arguments to make. Usage: --make=\"args...\". Defaults to \"-j <cpu count>\"")
        parser.add_argument("--lib-rpath", type=str, nargs='*',
                            help="Add run-time search path(s) for RGL library. $ORIGIN (actual library path) is added by default.")
    if on_windows():
        parser.add_argument("--ninja", type=str, default=f"-j{os.cpu_count()}", dest="build_args",
                            help="Pass arguments to ninja. Usage: --ninja=\"args...\". Defaults to \"-j <cpu count>\"")
    args = parser.parse_args()

    # Install dependencies for PCL extension
    if args.install_pcl_deps:
        # Clone vcpkg
        if not os.path.isdir(cfg.VCPKG_INSTALL_DIR):
            if on_linux() and not inside_docker():  # Inside docker already installed
                print("Installing dependencies for vcpkg...")
                run_system_command("sudo apt update")
                run_system_command("sudo apt install git curl zip unzip tar freeglut3-dev libglew-dev libglfw3-dev")
            run_subprocess_command(f"git clone -b {cfg.VCPKG_TAG} --single-branch --depth 1 https://github.com/microsoft/vcpkg {cfg.VCPKG_INSTALL_DIR}")
        # Bootstrap vcpkg
        if not os.path.isfile(os.path.join(cfg.VCPKG_INSTALL_DIR, cfg.VCPKG_EXEC)):
            run_subprocess_command(f"{os.path.join(cfg.VCPKG_INSTALL_DIR, cfg.VCPKG_BOOTSTRAP)}")

        # Install dependencies via vcpkg
        run_subprocess_command(f"{os.path.join(cfg.VCPKG_INSTALL_DIR, cfg.VCPKG_EXEC)} install --clean-after-build pcl[core,visualization]:{cfg.VCPKG_TRIPLET}")
        return 0

    # Check CUDA
    def is_cuda_version_ok():
        nvcc_process = subprocess.run("nvcc --version", shell=True, stdout=subprocess.PIPE)
        nvcc_ver_match = re.search("V[0-9]+.[0-9]+.[0-9]+", nvcc_process.stdout.decode("utf-8"))
        if not nvcc_ver_match:
            raise RuntimeError("CUDA not found")
        major = int(nvcc_ver_match[0].split(".")[0][1:])  # [1:] to remove char 'v'
        minor = int(nvcc_ver_match[0].split(".")[1])
        patch = int(nvcc_ver_match[0].split(".")[2])
        print(f"Found CUDA {major}.{minor}.{patch}")
        for (actual, expected) in [(major, cfg.CUDA_MIN_VER_MAJOR), (minor, cfg.CUDA_MIN_VER_MINOR), (patch, cfg.CUDA_MIN_VER_PATCH)]:
            if actual > expected:
                return True
            if actual < expected:
                return False
        return True

    if not is_cuda_version_ok():
        raise RuntimeError(f"CUDA version not supported! Get CUDA {cfg.CUDA_MIN_VER_MAJOR}.{cfg.CUDA_MIN_VER_MINOR}.{cfg.CUDA_MIN_VER_PATCH}+")

    # Check OptiX_INSTALL_DIR
    if os.environ["OptiX_INSTALL_DIR"] == "":
        raise RuntimeError("OptiX not found! Make sure you have exported environment variable OptiX_INSTALL_DIR")

    # Check extension requirements
    if args.with_pcl and not os.path.isdir(cfg.VCPKG_INSTALL_DIR):
        raise RuntimeError("PCL extension requires dependencies to be installed: run this script with --install-pcl-deps flag")

    # Go to script directory
    os.chdir(sys.path[0])

    # Prepare build directory
    if args.clean_build and os.path.isdir(args.build_dir):
        shutil.rmtree(args.build_dir, ignore_errors=True)
    if not os.path.isdir(args.build_dir):
        os.makedirs(args.build_dir)

    # Extend Path with libRobotecGPULidar location to link tests properly during the build on Windows
    if on_windows():
        os.environ["Path"] = os.environ["Path"] + ";" + os.path.join(os.getcwd(), args.build_dir)

    # Build
    if args.with_ros2_standalone:
        args.with_ros2 = True
    cmake_args = [
        f"-DCMAKE_TOOLCHAIN_FILE={os.path.join(cfg.VCPKG_INSTALL_DIR, 'scripts', 'buildsystems', 'vcpkg.cmake') if args.with_pcl else ''}",
        f"-DVCPKG_TARGET_TRIPLET={cfg.VCPKG_TRIPLET if args.with_pcl else ''}",
        f"-DRGL_BUILD_PCL_EXTENSION={'ON' if args.with_pcl else 'OFF'}",
        f"-DRGL_BUILD_ROS2_EXTENSION={'ON' if args.with_ros2 else 'OFF'}",
        f"-DRGL_BUILD_UDP_EXTENSION={'ON' if args.with_udp else 'OFF'}",
    ]

    if on_linux():
        # Set rpaths
        linker_rpath_flags = ["-Wl,-rpath=\\$ORIGIN"]  # add directory in which an RGL library is located
        if args.lib_rpath is not None:
            for rpath in args.lib_rpath:
                rpath = rpath.replace("$ORIGIN", "\\$ORIGIN")  # cmake should not treat this as variable
                linker_rpath_flags.append(f"-Wl,-rpath={rpath}")
        cmake_args.append(f"-DCMAKE_SHARED_LINKER_FLAGS=\"{' '.join(linker_rpath_flags)}\"")

    # Append user args, possibly overwriting
    cmake_args.append(args.cmake)

    cmake_args = " ".join(cmake_args)
    run_subprocess_command(f"cmake -B {args.build_dir} -G {cfg.CMAKE_GENERATOR} {cmake_args}")
    run_subprocess_command(f"cmake --build {args.build_dir} -- {args.build_args}")

    if args.with_ros2_standalone:
        # Build RobotecGPULidar_ros2_standalone project to find and install all dependent ROS2 libraries and their dependencies
        # It cannot be added as a subdirectory of RobotecGPULidar project because there is a conflict in the same libraries required by RGL and ROS2
        # RGL takes them from vcpkg as statically linked objects while ROS2 standalone required them as a shared objects
        ros2_standalone_cmake_args = f"-DCMAKE_INSTALL_PREFIX={os.path.join(os.getcwd(), args.build_dir)}"
        run_subprocess_command(f"cmake ros2_standalone -B {args.build_dir}/ros2_standalone -G {cfg.CMAKE_GENERATOR} {ros2_standalone_cmake_args}")
        run_subprocess_command(f"cmake --install {args.build_dir}/ros2_standalone")


def on_linux():
    return platform.system() == "Linux"


def on_windows():
    return platform.system() == "Windows"


def inside_docker():
    path = "/proc/self/cgroup"
    return (
        os.path.exists("/.dockerenv") or
        os.path.isfile(path) and any("docker" in line for line in open(path))
    )


def run_subprocess_command(command: str, shell=True, stderr=sys.stderr, stdout=sys.stdout):
    print(f"Executing command: '{command}'")
    process = subprocess.Popen(command, shell=shell, stderr=stderr, stdout=stdout)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Failed to execute command: '{command}'")


def run_system_command(command: str):
    print(f"Executing command: '{command}'")
    if os.system(command) != 0:
        raise RuntimeError(f"Failed to execute command: '{command}'")


if __name__ == "__main__":
    sys.exit(main())
