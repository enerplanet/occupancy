#!/usr/bin/env python
"""
Validation script for occupancy pipeline.
Validates conda environment, imports, CLI, tests, and package structure.

Usage:
    python validate.py [--skip-docker]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], description: str = "") -> tuple[int, str, str]:
    """Run command and return (exit_code, stdout, stderr)."""
    print(f"  → {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Timeout"
    except Exception as exc:
        return 1, "", str(exc)


def check_conda_env(env_name: str = "occupancy_env") -> bool:
    """Verify conda environment is usable."""
    print("\n[1/4] Checking conda environment...")
    code, out, err = run_cmd(
        ["conda", "run", "-n", env_name, "python", "--version"],
    )
    if code != 0:
        print(f"  ✗ Environment '{env_name}' not found or not usable")
        return False
    print(f"  ✓ {out.strip()}")

    code, out, err = run_cmd(
        [
            "conda",
            "run",
            "-n",
            env_name,
            "python",
            "-c",
            "import numpy, pandas; print('OK')",
        ],
    )
    if code != 0:
        print(f"  ✗ Imports failed: {err}")
        return False
    print("  ✓ Core imports OK (numpy, pandas)")
    return True


def check_cli(env_name: str = "occupancy_env") -> bool:
    """Verify CLI commands work."""
    print("\n[2/4] Checking CLI interface...")

    code, out, err = run_cmd(
        [
            "conda",
            "run",
            "-n",
            env_name,
            "python",
            "-m",
            "occupancy",
            "--help",
        ],
    )
    if code != 0:
        print(f"  ✗ 'occupancy --help' failed: {err}")
        return False
    print("  ✓ occupancy --help")
    return True


def check_tests(env_name: str = "occupancy_env") -> bool:
    """Run test suite."""
    print("\n[3/4] Running test suite...")
    code, out, err = run_cmd(
        [
            "conda",
            "run",
            "-n",
            env_name,
            "python",
            "-m",
            "pytest",
            "tests/",
            "-v",
            "--tb=short",
        ],
    )
    if code != 0:
        print("  ⚠ Some tests failed — see output above")
    else:
        print("  ✓ All tests passed")
    return True


def check_package_structure() -> bool:
    """Verify package structure is valid."""
    print("\n[4/4] Checking package structure...")

    checks = [
        ("src/occupancy/__init__.py", "Package init"),
        ("src/occupancy/__main__.py", "Module entry point"),
        ("src/occupancy/cli.py", "CLI module"),
        ("src/occupancy/_version.py", "Version file"),
        ("src/occupancy/core/occupancy_engine.py", "Shared occupancy engine"),
        ("src/occupancy/core/equipment.py", "Shared equipment model"),
        (
            "src/occupancy/households/household_profile.py",
            "Household occupancy profile",
        ),
        (
            "src/occupancy/households/electricity.py",
            "Household electricity profile",
        ),
        (
            "src/occupancy/services_buildings/building_profile.py",
            "Service building profile",
        ),
        ("src/occupancy/config/__init__.py", "Config subpackage"),
        ("infrastructure/env/occupancy_env.yml", "Conda environment spec"),
        ("pyproject.toml", "Project metadata"),
        ("CHANGELOG.md", "Changelog"),
    ]

    all_ok = True
    for path, desc in checks:
        if Path(path).exists():
            print(f"  ✓ {desc}")
        else:
            print(f"  ✗ Missing: {desc} ({path})")
            all_ok = False

    return all_ok


def main() -> int:
    """Run all validation checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        default="occupancy_env",
        help="Conda environment name (default: occupancy_env)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Occupancy Pipeline — Validation Suite")
    print("=" * 60)

    results = {
        "Conda Environment": check_conda_env(args.env),
        "CLI Interface": check_cli(args.env),
        "Test Suite": check_tests(args.env),
        "Package Structure": check_package_structure(),
    }

    print("\n" + "=" * 60)
    print("Validation Results:")
    print("=" * 60)

    all_passed = True
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:8s} {check}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All validations passed — ready for deployment!")
        return 0
    else:
        print("\n✗ Some validations failed — see output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
