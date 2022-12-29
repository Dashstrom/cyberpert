import re
from typing import Any, Dict, Iterator, List

import orjson
from lxml import etree

from .utils import TqdmIO, cache_json_zip, ftqdm

CVE_FETCH_URL = "https://nvd.nist.gov/vuln/data-feeds#JSON_FEED"
CVE_BASE_URL = "https://static.nvd.nist.gov/feeds/json/cve/1.1"
CPE_URL = (
    "https://nvd.nist.gov/feeds/xml/cpe/dictionary/"
    "official-cpe-dictionary_v2.3.xml.zip"
)


@cache_json_zip
def fetch_cpes() -> List[Dict[str, Any]]:
    """Fetch all CPE from nvd.nist.gov"""
    with TqdmIO(CPE_URL) as io:
        raw = io.download_zip(CPE_URL)
    print("Loading etree")
    root = etree.fromstring(raw)
    nsmap: Dict[str, str] = root.nsmap
    itercpe: Iterator[Any] = root.iterchildren()
    cpes = []
    next(itercpe)
    for cpe_item in ftqdm(itercpe, desc="Iterate over CPE"):
        title_ele = cpe_item.find("title", namespaces=nsmap)
        title = None if title_ele is None else title_ele.text
        cpe23uri_ele = cpe_item.find("cpe-23:cpe23-item", namespaces=nsmap)
        cpe23uri = None if cpe23uri_ele is None else cpe23uri_ele.get("name")
        references = [
            {"href": ref.get("href"), "name": ref.text}
            for ref in cpe_item.findall(
                "references/reference", namespaces=nsmap
            )
        ]
        cpe = {"title": title, "cpe23Uri": cpe23uri, "references": references}
        cpes.append(cpe)
    return cpes


@cache_json_zip
def fetch_cves() -> List[Dict[str, Any]]:
    """Fetch all CVE from nvd.nist.gov."""
    print(f"Feching CVE from {CVE_FETCH_URL}")
    with TqdmIO("Download CVE") as io:
        response = io.download_file(CVE_FETCH_URL).decode("utf8")
    filenames = re.findall(r"nvdcve-1.1-2[0-9]*\.json\.zip", response)
    filenames = sorted(filenames)
    filenames_progressbar = ftqdm(
        filenames,
        desc=f"Downloading CVE from {CVE_BASE_URL}",
        unit="file",
        position=1,
    )
    cves = []
    for filename in filenames_progressbar:
        with TqdmIO(filename) as io:
            data = io.download_zip(f"{CVE_BASE_URL}/{filename}")
            io.desc("Deserialize")
            cve_dict: Dict[str, Any] = orjson.loads(data)
            io.desc("Scanning")
            for cve in cve_dict["CVE_Items"]:
                cves.append(cve)
    return cves
