#!/usr/bin/env python3
"""
Test runner script for JFIP Web UI routes.
"""
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd):
    """Run a command and return the result."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run tests for JFIP Web UI")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--file", "-f", help="Run specific test file")
    parser.add_argument("--function", "-fn", help="Run specific test function")
    parser.add_argument("--marker", "-m", help="Run tests with specific marker")
    parser.add_argument("--skip-slow", action="store_true", help="Skip slow tests")
    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration-only", action="store_true", help="Run only integration tests")
    parser.add_argument("--list", "-l", action="store_true", help="List all tests")
    
    args = parser.parse_args()
    
    # Build pytest command
    cmd_parts = ["python", "-m", "pytest"]
    
    if args.verbose:
        cmd_parts.append("-v")
    
    if args.coverage:
        cmd_parts.extend(["--cov=web", "--cov-report=html", "--cov-report=term"])
    
    if args.file:
        cmd_parts.append(f"tests/{args.file}")
    else:
        cmd_parts.append("tests/")
    
    if args.function:
        cmd_parts.append(f"-k {args.function}")
    
    if args.marker:
        cmd_parts.extend(["-m", args.marker])
    
    if args.skip_slow:
        cmd_parts.extend(["-m", "not slow"])
    
    if args.unit_only:
        cmd_parts.extend(["-m", "unit"])
    
    if args.integration_only:
        cmd_parts.extend(["-m", "integration"])
    
    if args.list:
        cmd_parts.append("--collect-only")
    
    cmd = " ".join(cmd_parts)
    
    print(f"Running: {cmd}")
    print("-" * 50)
    
    # Run the command
    returncode, stdout, stderr = run_command(cmd)
    
    if stdout:
        print(stdout)
    
    if stderr:
        print("STDERR:", stderr)
    
    if returncode == 0:
        print("\n✅ Tests passed!")
    else:
        print(f"\n❌ Tests failed with return code {returncode}")
    
    return returncode


if __name__ == "__main__":
    sys.exit(main())
