import operator
import re
from typing import Any, Callable, Dict, Generator, List, Optional

from .utils import Facts, Rule, ver

OPERATORS: Dict[str, Callable[..., Any]] = {}
OPERATORS.update(
    {
        "===": operator.eq,
        "==": operator.eq,
        ">=": operator.ge,
        "<=": operator.le,
        ">": operator.gt,
        "<": operator.lt,
        "~=": operator.ge,
        "!=": operator.ne,
        ">==": operator.ge,
    }
)
OPERATORS.update(
    {
        ">=~": lambda x, y: ver(x) >= ver(y),
        "<=~": lambda x, y: ver(x) <= ver(y),
        ">~": lambda x, y: ver(x) > ver(y),
        "<~": lambda x, y: ver(x) < ver(y),
    }
)
OPERATORS.update(
    {
        "or": lambda x, y: x or y,
        "and": lambda x, y: x and y,
    }
)


def never(*args: Any) -> bool:  # pylint: disable=unused-argument
    """Default operator."""
    return False


def match_rule(condition: Any, facts: Facts) -> bool:
    """Evaluate condition with facts."""
    prev: Any = None
    func: Optional[Callable[..., Any]] = None
    for part in condition:
        if func is None:
            if prev is None:
                if isinstance(part, (list, tuple)):
                    prev = match_rule(part, facts)
                else:
                    prev = facts.get(part)
            else:
                func = OPERATORS.get(part, never)
        else:
            if isinstance(part, (list, tuple)):
                actual = match_rule(part, facts)
            else:
                actual = part
            try:
                prev = func(prev, actual)  # pylint: disable=not-callable
            except TypeError:
                prev = False
            func = None
    return bool(prev)


class Engine:
    def __init__(self, rules: Any) -> None:
        self.rules = rules
        self.path = []
    def _matching_packages(self, facts: Facts) -> Generator[Rule, None, None]:
        """Specific matcher for python packages."""
        for fact, value in facts.items():
            requirements = (
                self.rules["packages"].get(fact.lower(), {}).get(value, {})
            )
            for name, constraints in requirements.items():
                for version in self.rules["packages"].get(name, {}).keys():
                    cmp_version = ver(version)
                    for (op, op_version) in constraints:
                        cmp_op_version = ver(op_version)
                        comparator = OPERATORS.get(op, never)
                        if not comparator(cmp_version, cmp_op_version):
                            break
                    else:
                        yield (
                            [fact, "==", value],
                            {name: version},
                        )

    def _matching(self, facts: Facts) -> Generator[Rule, None, None]:
        """Hight logic matcher."""
        for (condition, new_facts) in self.rules["rules"]:
            if match_rule(condition, facts):
                yield (condition, new_facts)

    def matching(self, facts: Facts) -> Generator[Rule, None, None]:
        """Return all rule that match facts."""
        yield from self._matching(facts)
        yield from self._matching_packages(facts)

    def explore(self, facts: Facts, but: Facts, chemin: List[str]=[]) -> List[str]:
        """Start to facts and return a path to but."""
        for rule in self.matching(facts):
            if not rule[1]:
                continue
            if(list(but.values())[0] in rule[1].values() and list(but.keys())[0] in rule[1].keys()):
                way = chemin.copy()
                way.append(rule)
                self.path.append(way)
            else:
                new_chemin = chemin.copy()  # copy the list here
                new_chemin.append(rule[0])
                self.explore(rule[1], but, new_chemin)
        return self.path
