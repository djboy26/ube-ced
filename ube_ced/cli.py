"""ube-ced run <system.yaml> [--basket basket.yaml] [--out DIR] [--draws N] [--seed S] [--could-not-obtain TEXT]
   ube-ced battery <system.yaml> [--basket basket.yaml]
   ube-ced conform <model_dir>"""
from __future__ import annotations
import argparse, json, sys
from .system import load_system, load_basket
from .report import build_report, write_report
from .battery import battery
from .conform import conform
from .records import ValidationError


def main(argv=None):
    p = argparse.ArgumentParser(prog="ube-ced", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("system"); r.add_argument("--basket"); r.add_argument("--out", default="report_out")
    r.add_argument("--draws", type=int, default=10_000); r.add_argument("--seed", type=int, default=0); r.add_argument("--could-not-obtain", default="")
    b = sub.add_parser("battery"); b.add_argument("system"); b.add_argument("--basket")
    c = sub.add_parser("conform"); c.add_argument("model_dir")
    a = p.parse_args(argv)
    try:
        if a.cmd == "run":
            s = load_system(a.system)
            basket = load_basket(a.basket, s) if a.basket else None
            rep = build_report(s, basket, draws=a.draws, seed=a.seed, could_not_obtain=a.could_not_obtain)
            paths = write_report(rep, a.out)
            h = rep["headline"]
            print(f"{h['interval']['p05']:.4g} to {h['interval']['p95']:.4g} {h['unit']} (central {h['central']:.4g})")
            print("\n".join(paths.values()))
        elif a.cmd == "battery":
            res = battery(a.system, a.basket)
            for x in res:
                print(f"{'PASS' if x['pass'] else 'FAIL'}  {x['mutation']:55s} expected {x['expected']:17s} got {x['outcome']}")
            n = sum(1 for x in res if x["pass"]); print(f"{n}/{len(res)} passed")
            sys.exit(0 if n == len(res) else 1)
        elif a.cmd == "conform":
            res = conform(a.model_dir); print(json.dumps(res, indent=2)); sys.exit(0 if res["pass"] else 1)
    except ValidationError as ex:
        print("REFUSED (spec D2/D4):\n" + str(ex)); sys.exit(2)


if __name__ == "__main__":
    main()
