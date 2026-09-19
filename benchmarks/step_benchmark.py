#!/usr/bin/env python3
"""Benchmark for the croniter stepping hot path (get_next on a minute expression).

Usage:
    python3 benchmarks/step_benchmark.py run                      # print a raw summary
    python3 benchmarks/step_benchmark.py save PATH                # save results as JSON
    python3 benchmarks/step_benchmark.py check PATH [-t 0.15]     # compare against a baseline

The workload is fixed: 10000 forward iterations of the typical minute
expression "* * * * *" starting from a fixed base time, best-of-N repeats
(min is used because it is the most stable estimator of code cost).
No sleeping and no wall-clock-dependent inputs are involved.
"""

import argparse
import datetime
import json
import platform
import sys
import time

from croniter import croniter

EXPRESSION = "* * * * *"
BASE_TIME = datetime.datetime(2024, 1, 5, 12, 30)
DEFAULT_ITERATIONS = 10000
DEFAULT_REPEATS = 7
WARMUP_ITERATIONS = 500


def run_once(iterations):
    itr = croniter(EXPRESSION, BASE_TIME)
    start = time.perf_counter()
    for _ in range(iterations):
        itr.get_next()
    return time.perf_counter() - start


def environment_info():
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def benchmark(iterations=DEFAULT_ITERATIONS, repeats=DEFAULT_REPEATS):
    run_once(WARMUP_ITERATIONS)
    samples = [run_once(iterations) for _ in range(repeats)]
    best = min(samples)
    return {
        "expression": EXPRESSION,
        "base_time": BASE_TIME.isoformat(),
        "iterations": iterations,
        "repeats": repeats,
        "samples_seconds": samples,
        "best_seconds": best,
        "per_iteration_seconds": best / iterations,
        "environment": environment_info(),
    }


def print_summary(result):
    env = result["environment"]
    print(f"expression={result['expression']!r} iterations={result['iterations']} "
          f"repeats={result['repeats']}")
    print("samples_seconds=" + " ".join(f"{s:.4f}" for s in result["samples_seconds"]))
    print(f"best_seconds={result['best_seconds']:.4f} "
          f"per_iteration_seconds={result['per_iteration_seconds']:.6f}")
    print(f"environment: python={env['python']} ({env['implementation']}) "
          f"platform={env['platform']} machine={env['machine']}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "save", "check"):
        p = sub.add_parser(name)
        p.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
        p.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
        if name in ("save", "check"):
            p.add_argument("path")
        if name == "check":
            p.add_argument("--tolerance", "-t", type=float, default=0.15)
    args = parser.parse_args(argv)

    result = benchmark(args.iterations, args.repeats)
    print_summary(result)

    if args.command == "save":
        with open(args.path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"saved baseline to {args.path}")
        return 0

    if args.command == "check":
        with open(args.path) as f:
            baseline = json.load(f)
        base_best = baseline["best_seconds"]
        limit = base_best * (1 + args.tolerance)
        cur_best = result["best_seconds"]
        ratio = cur_best / base_best
        print(f"baseline_best_seconds={base_best:.4f} current_best_seconds={cur_best:.4f} "
              f"ratio={ratio:.3f} allowed<={1 + args.tolerance:.2f}")
        print(f"baseline_environment: {baseline['environment']}")
        if cur_best > limit:
            print(f"FAIL: stepping hot path is more than {args.tolerance:.0%} slower "
                  f"than baseline")
            return 1
        print("OK: within tolerance")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
