import re
import sys
from typing import Any, Dict, List, Tuple

from colorama import Fore, init

from .data import get_rules
from .engine import InferenceEngine
from .pypi import parse_requirements
from .utils import PIPED

init()


RE_SPLIT = re.compile(r"\s*[\n\r]+\s*")


def recursive_requirements_parsing(
    requirements: List[str],
) -> Dict[str, Tuple[str, List[Tuple[str, str]]]]:
    """Parse requirements and requirements inside files."""
    i = 0
    parsed: Dict[str, Tuple[str, List[Tuple[str, str]]]] = {}
    while i < len(requirements):
        req = requirements[i].strip()
        if not req:
            continue
        elif req == "-r":
            path = requirements[i + 1]
        elif req.startswith("-r "):
            path = req.split("-r")[1].strip()
        else:
            path = None
        if path:
            with open(path, "r", encoding="utf8") as file:
                subparsed = recursive_requirements_parsing(
                    RE_SPLIT.split(file.read().strip())
                )
                for key, line_constraints in subparsed.items():
                    try:
                        parsed[key][1].extend(line_constraints[1])
                    except KeyError:
                        parsed[key] = line_constraints
            i += 1
        else:
            try:
                key, constraints = next(
                    iter(parse_requirements([req]).items())
                )
                try:
                    parsed[key][1].extend(constraints)
                except KeyError:
                    parsed[key] = (req, constraints)
            except StopIteration:
                pass  # No fallback, skip silenty
        i += 1
    return parsed


def recursive_join(obj: Any) -> str:
    """Make pretty condition."""
    if isinstance(obj, (tuple, list)):
        return " ".join(recursive_join(element) for element in obj)
    else:
        return str(obj)


def app() -> None:
    """Main function for calling cli."""
    error = 0
    requirements = sys.argv[1:]
    if not requirements:
        requirements = list(sys.stdin)
    if requirements:
        engine = InferenceEngine(rules=get_rules())
        for req, (line, constraint) in recursive_requirements_parsing(
            requirements
        ).items():
            if not PIPED:
                print(f"{Fore.YELLOW}{line}{Fore.RESET}", end="", flush=True)
            for version in engine.broadcaster((req, constraint)):
                try:
                    path = next(
                        iter(
                            engine.forward_chaining(
                                {req: version}, {"$vuln": True}
                            )
                        )
                    )
                    pretty_path = " → ".join(
                        recursive_join(part) for part in path[:-1]
                    )
                    pretty_path += " → https://nvd.nist.gov/vuln/detail/"
                    pretty_path += path[-1]["$cve"]
                    for src, dst in (
                        (">=~", "≥"),
                        ("<=~", "≤"),
                        (">~", ">"),
                        ("<~", "<"),
                        ("==", "="),
                    ):
                        pretty_path = pretty_path.replace(src, dst)
                    print(
                        f"\r{Fore.RED}{line}{Fore.RESET}  "
                        f"{Fore.LIGHTBLACK_EX}# {pretty_path}{Fore.RESET}"
                    )
                    error = 1
                    break
                except StopIteration:
                    pass
            else:
                print(f"\r{Fore.GREEN}{line}{Fore.RESET}")
    else:
        error = 2
    sys.exit(error)
