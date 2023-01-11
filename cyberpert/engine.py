import operator
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Tuple,
)

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


def condition_matching_facts(condition: Any, facts: Facts) -> bool:
    """Evaluate condition with facts."""
    prev: Any = None
    func: Optional[Callable[..., Any]] = None
    for part in condition:
        if func is None:
            if prev is None:
                if isinstance(part, (list, tuple)):
                    prev = condition_matching_facts(part, facts)
                else:
                    prev = facts.get(part)
            else:
                func = OPERATORS.get(part, never)
        else:
            if isinstance(part, (list, tuple)):
                actual = condition_matching_facts(part, facts)
            else:
                actual = part
            try:
                prev = func(prev, actual)  # pylint: disable=not-callable
            except TypeError:
                prev = False
            func = None
    return bool(prev)


class InferenceEngine:
    def __init__(self, rules: Any) -> None:
        self.rules = rules
        self._matching_cache: Dict[Any, List[Any]] = {}

    def _rules_matching_packages(
        self, facts: Facts
    ) -> Generator[Rule, None, None]:
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
                            (fact, "==", value),
                            {name: version},
                        )

    def _rules_matching(self, facts: Facts) -> Generator[Rule, None, None]:
        """Hight logic rules matcher."""
        for (condition, new_facts) in self.rules["rules"]:
            if condition_matching_facts(condition, facts):
                yield (condition, new_facts)

    def rules_matching(self, facts: Facts) -> Generator[Rule, None, None]:
        """Return all rule that match facts."""
        yield from self._rules_matching(facts)
        yield from self._rules_matching_packages(facts)

    def forward_chaining(self, facts: Facts, but: Facts) -> Iterable[Any]:
        """Start to facts and return a path to but."""
        key = (tuple(facts.items()), tuple(but.items()))
        try:
            yield from self._matching_cache[key]
        except KeyError:
            paths: List[Any] = []
            if all(
                facts.get(key, None) == value for key, value in but.items()
            ):
                paths.append((facts,))
                yield (facts,)
            else:
                for rule in self.rules_matching(facts):
                    for subpath in self.forward_chaining(rule[1], but):
                        path = (rule[0], *subpath)
                        paths.append(path)
                        yield path
            self._matching_cache[key] = paths

    def broadcaster(
        self, requirement: Tuple[str, List[Tuple[str, str]]]
    ) -> Generator[str, None, None]:
        """Return all version matching constraints."""
        requirements = self.rules["packages"].get(requirement[0].lower(), {})
        for version in requirements.keys():
            cmp_version = ver(version)
            for (op, op_version) in requirement[1]:
                cmp_op_version = ver(op_version)
                comparator = OPERATORS.get(op, never)
                if not comparator(cmp_version, cmp_op_version):
                    break
            else:
                yield version
