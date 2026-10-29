"""Reality check: do the packages the AI imported actually exist on PyPI?"""

import ast
import sys
from dataclasses import dataclass

import requests

# Import names that differ from their PyPI package names.
ALIASES = {
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "Crypto": "pycryptodome",
    "attr": "attrs",
    "google": "google-api-core",
}


@dataclass
class PackageCheck:
    module: str
    package: str
    exists: bool
    detail: str


def imported_modules(code: str) -> list[str]:
    """Top-level module names imported by the code, in order, without duplicates."""
    tree = ast.parse(code)
    seen: list[str] = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            top = name.split(".")[0]
            if top not in seen:
                seen.append(top)
    return seen


def check_packages(code: str, timeout: float = 5.0) -> list[PackageCheck]:
    results = []
    for module in imported_modules(code):
        if module in sys.stdlib_module_names:
            continue
        package = ALIASES.get(module, module)
        try:
            r = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=timeout)
        except requests.RequestException as e:
            results.append(PackageCheck(module, package, True, f"Could not reach PyPI: {e}"))
            continue
        if r.status_code == 200:
            info = r.json()["info"]
            results.append(PackageCheck(module, package, True, f"Found on PyPI (latest {info['version']})"))
        elif r.status_code == 404:
            results.append(PackageCheck(module, package, False, "Not on PyPI: the AI may have invented this package"))
        else:
            results.append(PackageCheck(module, package, True, f"PyPI returned HTTP {r.status_code}"))
    return results
