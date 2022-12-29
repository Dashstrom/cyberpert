from .data import get_rules
from .engine import Engine


def cli() -> None:
    engine = Engine(rules=get_rules())
    for rule in engine.matching({"autobahn": "20.12.3"}):
        print(rule)
    for rule in engine.matching({"cryptography": "3.0"}):
        print(rule)
    path = engine.explore({"autobahn": "20.12.3"}, {"$vuln": True})
    print(path)


if __name__ == "__main__":
    cli()
