#!/usr/bin/env python3
"""Benchmark for the croniter stepping hot path.

Hot path under test: a typical one-minute expression stepped forward
10_000 times from a fixed (naive) base time::

    itr = croniter("*/1 * * * *", datetime(2010, 1, 23, 12, 18))
    for _ in range(10_000):
        itr.get_next()

Usage (from the repository root):

    # measure the current working tree and print a raw summary
    python3 benchmarks/bench_step.py

    # record the current working tree as the baseline
    python3 benchmarks/bench_step.py --save-baseline benchmarks/baseline.json

    # compare the current working tree against a saved baseline
    python3 benchmarks/bench_step.py --baseline benchmarks/baseline.json

Regenerating the committed baseline against the pre-refactor code
(commit a487265, "Initial environment snapshot")::

    git worktree add /tmp/croniter-baseline a487265
    PYTHONPATH=/tmp/croniter-baseline/src \\
        python3 benchmarks/bench_step.py --save-baseline benchmarks/baseline.json
    git worktree remove /tmp/croniter-baseline

The benchmark only uses the public croniter API, so the same script runs
unchanged against any revision of the sources.  No sleeps and no wall-clock
dependent inputs: the base time is fixed and only CPU time spent in
``get_next`` is measured.
"""

import argparse
import json
import platform
import sys
from datetime import datetime
from timeit import Timer

EXPRESSION = "*/1 * * * *"
ITERATIONS = 10_000
ROUNDS = 5
DEFAULT_TOLERANCE = 0.15


def run_benchmark(iterations=ITERATIONS, rounds=ROUNDS):
    from croniter import croniter

    def bench():
        itr = croniter(EXPRESSION, datetime(2010, 1, 23, 12, 18))
        for _ in range(iterations):
            itr.get_next()

    timer = Timer(bench)
    samples = [timer.timeit(1) for _ in range(rounds)]
    return {
        "expression": EXPRESSION,
        "iterations": iterations,
        "rounds": rounds,
        "samples_seconds": samples,
        "min_seconds": min(samples),
        "median_seconds": sorted(samples)[len(samples) // 2],
        "per_iteration_seconds": min(samples) / iterations,
    }


def environment_info():
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-baseline", metavar="PATH", help="write results as baseline JSON")
    parser.add_argument("--baseline", metavar="PATH", help="compare against baseline JSON")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="allowed slowdown fraction vs baseline (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    result = run_benchmark()
    result["environment"] = environment_info()

    summary = (
        "expression={expression} iterations={iterations} rounds={rounds} "
        "min={min_seconds:.4f}s median={median_seconds:.4f}s "
        "per_iter={per_iteration_seconds:.2e}s".format(**result)
    )
    print("benchmark:", summary)
    print("environment:", json.dumps(result["environment"]))

    if args.save_baseline:
        with open(args.save_baseline, "w") as fh:
            json.dump(result, fh, indent=2, sort_keys=True)
        print(f"baseline saved to {args.save_baseline}")

    if args.baseline:
        with open(args.baseline) as fh:
            baseline = json.load(fh)
        limit = baseline["per_iteration_seconds"] * (1 + args.tolerance)
        current = result["per_iteration_seconds"]
        ratio = current / baseline["per_iteration_seconds"]
        print(
            "compare: current={:.2e}s baseline={:.2e}s ratio={:.3f} "
            "allowed<={:.3f}".format(current, baseline["per_iteration_seconds"], ratio, 1 + args.tolerance)
        )
        if current > limit:
            print(
                "FAIL: stepping hot path is more than {:.0%} slower than baseline".format(
                    args.tolerance
                )
            )
            return 1
        print("OK: within {:.0%} of baseline".format(args.tolerance))
    return 0


if __name__ == "__main__":
    sys.exit(main())
