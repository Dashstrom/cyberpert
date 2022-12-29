import os
import re
from collections import defaultdict
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple

import orjson
from google.cloud import bigquery
from packaging.version import InvalidVersion

from .utils import cache_json_zip, ftqdm, ver

GPC_KEY = "GOOGLE_APPLICATION_CREDENTIALS"
os.environ.setdefault(GPC_KEY, "./creds.json")


PYPI = re.compile(r"https://pypi\.org/project/(?P<name>[^/]+).*")
PATTERN_URL_COMPLETE = (
    r"(https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}"
    r"\b[-a-zA-Z0-9@:%_\+.~#?&\/=]*)"
)
REGEX_URL_COMPLETE = re.compile(PATTERN_URL_COMPLETE)

PATTERN_URL_QUERY = (
    r"(?:https?:\/\/)?(?:www\.)?([-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}"
    r"\b[-a-zA-Z0-9@:%_\+.~#?&\/=]*)"
)
REGEX_URL_QUERY = re.compile(PATTERN_URL_QUERY)

PATTERN_URL_GITHUB = (
    r"(?:https?:\/\/)?(?:www\.)?"
    r"(github\.com\/[\-._a-zA-ZA-Z]+\/[\-._a-zA-ZA-Z]+)"
)
REGEX_URL_GITHUB = re.compile(PATTERN_URL_GITHUB)

PATTERN_URL_PYPI = (
    r"(?:https?:\/\/)?(?:www\.)?(pypi\.org\/project\/[\-._a-zA-ZA-Z]+)"
)
REGEX_URL_PYPI = re.compile(PATTERN_URL_PYPI)

RE_VERSION = re.compile(r"((?:.==?)|<|>)\s*([^~!=<>]+)")
RE_REQUIREMENTS = re.compile(
    r"([a-zA-Z0-9\-_\.]+)"
    r"(?:\[([a-zA-Z0-9\-_\., ]+)\])?"
    r"(?:\s*\(?([^;\)]+)\)?)?"
    r"(?:\s*;\s*(.+))?"
)
Requirements = Dict[str, List[Tuple[str, str]]]
PackagesRequirements = Dict[str, Dict[str, Requirements]]


def parse_requirements(
    requirements: List[str],
) -> Requirements:
    """Perform best effort for generate requirements."""
    reqs: Dict[str, List[Tuple[str, str]]] = {}
    for req in requirements:
        if req.startswith("git+"):
            continue
        match = RE_REQUIREMENTS.fullmatch(req)
        if match:
            req_name, _, req_expr_versions, req_extra = match.groups()
            if req_extra:
                continue
            if req_expr_versions and req_expr_versions.strip():
                req_versions = req_expr_versions.split(",")
                for req_version in req_versions:
                    sub_versions = RE_VERSION.findall(req_version.strip())
                    if sub_versions:
                        for cmp, val in sub_versions:
                            if not cmp or not val:
                                continue
                            try:
                                ver(val)
                            except InvalidVersion:
                                continue
                            key = (cmp, val.lower())
                            try:
                                old_reqs = reqs[req_name]
                                if key not in old_reqs:
                                    old_reqs.append(key)
                            except KeyError:
                                reqs[req_name] = [key]
                    else:
                        try:
                            reqs[req_name]
                        except KeyError:
                            reqs[req_name] = []
            else:
                try:
                    reqs[req_name]
                except KeyError:
                    reqs[req_name] = []

    return reqs


def _bigquery_request(
    query: str,
    args: Optional[List[bigquery.ArrayQueryParameter]] = None,
    silent: bool = False,
) -> Generator[Any, None, None]:
    """Perform a bigquery request."""
    with open(os.environ[GPC_KEY], "r", encoding="utf8") as file:
        config = orjson.loads(file.read())
        name = config["project_id"]
    client = bigquery.Client(project=name)
    if not silent:
        print("Running BigQuery ...")
    options: Any = {}
    if args:
        options["job_config"] = bigquery.QueryJobConfig(query_parameters=args)
    query_job = client.query(query, **options)
    if not silent:
        print("Wait for results ...")
    rows = query_job.result()
    cost_dollars = (query_job.total_bytes_processed / 1024**4) * 5
    if not silent:
        print(f"You pay {cost_dollars:.5f} $ for this request")
        progress: Any = ftqdm(
            rows, total=rows.total_rows, desc="Iterate result"
        )
    else:
        progress = rows
    for row in progress:
        yield row


@cache_json_zip
def fetch_packages() -> PackagesRequirements:
    """Fetch all packages requirements per version."""
    packages: PackagesRequirements = {}
    query = """
    SELECT
        name,
        version,
        ARRAY_CONCAT_AGG(
            ARRAY_CONCAT(requires, requires_dist, requires_external)
        ) as requirements
    FROM `bigquery-public-data.pypi.distribution_metadata`
    GROUP by name, version
    """
    for row in _bigquery_request(query):
        try:
            versions = packages[row.name.lower()]
        except KeyError:
            versions = packages[row.name.lower()] = {}
        try:
            # Skip all invalid version
            ver(row.version)
            versions[row.version] = parse_requirements(row.requirements)
        except InvalidVersion:
            pass
    return packages


def fetch_references(
    references: Optional[Iterable[str]] = None,
) -> Generator[Tuple[str, str], None, None]:
    """Fetch all package with given references."""
    references = references or []
    core_references: Dict[str, Set[str]] = defaultdict(set)
    for ref in references:
        key = ref.lower().rstrip("/")
        match = REGEX_URL_QUERY.search(key)
        if match:
            key = match.group(1).rstrip("/")
        match = REGEX_URL_GITHUB.search(key)
        if match:
            key = match.group(1).rstrip("/")
        match = REGEX_URL_PYPI.search(key)
        if match:
            key = match.group(1).rstrip("/")
        core_references[key].add(ref)
    query = f"""
    SELECT name, ANY_VALUE(url) as url
    FROM (
        SELECT
            name,
            (
                SELECT url FROM (
                    SELECT url FROM (
                        SELECT
                            REGEXP_REPLACE(
                                COALESCE(
                                REGEXP_EXTRACT(url, r\"{PATTERN_URL_GITHUB}\"),
                                REGEXP_EXTRACT(url, r\"{PATTERN_URL_PYPI}\"),
                                REGEXP_EXTRACT(url, r\"{PATTERN_URL_QUERY}\")
                                ),
                                r'\\*$',
                                ''
                            ) as url
                        FROM UNNEST(
                            ARRAY_CONCAT(
                                ARRAY(SELECT home_page),
                                ARRAY(SELECT download_url),
                                ARRAY(
                                    SELECT REGEXP_EXTRACT(
                                        project_url,
                                        r\"{PATTERN_URL_COMPLETE}\"
                                    )
                                    FROM UNNEST(project_urls) AS project_url
                                )
                            )
                        ) as url
                    )
                    WHERE url IN UNNEST(@references)
                ) as url
                LIMIT 1
            ) as url
        FROM `bigquery-public-data.pypi.distribution_metadata`
    )
    WHERE url IS NOT NULL
    GROUP BY name;
    """
    args = [
        bigquery.ArrayQueryParameter(
            name="references",
            array_type="STRING",
            values=list(core_references.keys()),
        )
    ]
    for row in _bigquery_request(query, args, silent=True):
        url = row[1]["url"]
        for core_url in core_references.get(url, set()):
            yield (row[0].lower(), core_url)
