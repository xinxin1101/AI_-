import argparse
import asyncio

from app.eval.runner import run_rag_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic RAG evaluation")
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run_rag_eval())
    print(report.model_dump_json(indent=2))
    if args.fail_on_threshold and not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
