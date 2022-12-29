from .data import get_rules
from .engine import Engine


def cli() -> None:
    engine = Engine(rules=get_rules())
    print("Begin first :\n")
    for rule in engine.matching({"autobahn": "20.12.3"}):
        print(rule)
    print("\nBegin second :\n")
    for rule in engine.matching({"pycparser": "2.10"}):
        print(rule)
    print("\nBegin exploration...\n")
    path = engine.explore({"autobahn": "20.12.3"}, {"$vuln": True})
    for x in path:
        print(x, "\n")
    #print(path)


if __name__ == "__main__":
    cli()
