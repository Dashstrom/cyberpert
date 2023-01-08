import zipfile
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple, Union

from packaging.version import InvalidVersion

from .nvd import fetch_cpes, fetch_cves
from .pypi import fetch_packages, fetch_references
from .utils import (
    DATA_PATH,
    Condition,
    Facts,
    TqdmIO,
    cache_json_zip,
    ftqdm,
    ranges_versions,
    ver,
)

RULES_PATH = DATA_PATH / "rules.json.zip"


def recursive_vendor_projects(nodes: List[Any]) -> Set[Tuple[str, ...]]:
    """Find all vendors and projects inside a cpe match."""
    vendor_projects = set()
    for node in nodes:
        for match in node["cpe_match"]:
            cpe23Uri: str = match["cpe23Uri"]
            vendor_project = tuple(cpe23Uri.split(":")[3:5])
            vendor_projects.add(vendor_project)
        vendor_projects |= recursive_vendor_projects(node["children"])
    return vendor_projects


def fetch_vendor_projects_per_packages() -> Dict[Tuple[str, ...], Set[str]]:
    """Find all vendors and projects related to a package."""
    cpes = fetch_cpes()
    references: Dict[str, Set[Tuple[str, ...]]] = defaultdict(set)
    for cpe in cpes:
        for reference in cpe["references"]:
            if reference["name"] != "Vendor":
                vendor_project: Tuple[str, ...] = tuple(
                    cpe["cpe23Uri"].split(":")[3:5]
                )
                references[reference["href"]].add(vendor_project)

    cves = fetch_cves()
    for cve in cves:
        urls = [
            ref["url"] for ref in cve["cve"]["references"]["reference_data"]
        ]
        for vendor_project in recursive_vendor_projects(
            cve["configurations"]["nodes"]
        ):
            for url in urls:
                references[url].add(vendor_project)

    vendor_projects_per_packages: Dict[Tuple[str, ...], Set[str]] = {}
    references_keys = list(references.keys())
    size = 50000
    for i in ftqdm(
        range(0, len(references_keys), size), desc="Searching references"
    ):
        for name, url in fetch_references(
            references_keys[i : i + size]  # noqa
        ):
            for vendor_project in references[url]:
                try:
                    packages = vendor_projects_per_packages[vendor_project]
                except KeyError:
                    packages = vendor_projects_per_packages[
                        vendor_project
                    ] = set()
                packages.add(name)
    return vendor_projects_per_packages


@cache_json_zip
def fetch_cves_per_packages() -> List[List[Union[Condition, Facts]]]:
    """Fetch all CVE per package using reference inside CVE and CPE."""
    requirements = fetch_packages()
    vendor_projects_per_packages = fetch_vendor_projects_per_packages()
    cves = fetch_cves()

    cves_per_packages: Dict[str, Dict[str, List[str]]] = {}
    for cve in ftqdm(cves, desc="Resolving cves"):
        cve_id = cve["cve"]["CVE_data_meta"]["ID"]
        for node in cve["configurations"]["nodes"]:
            if node["operator"] != "OR":
                continue
            for match in node["cpe_match"]:
                cpe23Uri: str = match["cpe23Uri"]
                vendor_project = tuple(cpe23Uri.split(":")[3:5])
                version, up = cpe23Uri.split(":")[5:7]
                try:
                    packages = vendor_projects_per_packages[vendor_project]
                except KeyError:
                    continue  # not a python package
                star_up = up == "*"
                no_up = up == "-"
                try:
                    v_ver = ver(
                        version if star_up or no_up else (version + up)
                    )
                except InvalidVersion:
                    continue
                for package in packages:
                    for pkg_ver in requirements[package].keys():
                        v_pkg_ver = ver(pkg_ver)
                        if star_up and v_ver.release != v_pkg_ver.release:
                            continue
                        if not star_up and v_pkg_ver != v_ver:
                            continue
                        try:
                            cve_packages = cves_per_packages[cve_id]
                        except KeyError:
                            cve_packages = cves_per_packages[cve_id] = {}
                        try:
                            if pkg_ver not in cve_packages[package]:
                                cve_packages[package].append(pkg_ver)
                        except KeyError:
                            cve_packages[package] = [pkg_ver]
    return [
        [
            ranges_versions(package, versions, requirements[package].keys()),
            {"$cve": cve_id, "$vuln": True},
        ]
        for cve_id, packages in cves_per_packages.items()
        for package, versions in packages.items()
    ]


def tuplize(array: Any) -> Tuple[Any, ...]:
    if isinstance(array, list):
        return tuple(tuplize(obj) for obj in array)
    return array  # type: ignore


def get_rules() -> Any:
    """Get or download all rules."""
    if RULES_PATH.exists():
        with TqdmIO("rules") as io:
            data = io.read_jsonzip(RULES_PATH)
    else:
        data = {
            "packages": fetch_packages(),
            "rules": fetch_cves_per_packages(),
        }
        with TqdmIO("rules") as io:
            io.write_jsonzip(RULES_PATH, data, zipfile.ZIP_LZMA)
    data["rules"] = tuplize(data["rules"])
    return data
