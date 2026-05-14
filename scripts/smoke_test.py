from __future__ import annotations

import argparse

from quackit.bootstrap import create_app_context
from quackit.models import MemoryType


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-path", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    context = create_app_context(database_path=args.database_path)
    service = context.service

    session = service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE,
        content="smoke memory",
        tags=["smoke"],
    )
    results = service.search_memory(query="smoke")
    fetched = service.get_memory(created.mem_id)
    ended = service.end_session(summary="smoke complete")

    require(session.id == ended.id, "session id mismatch after end_session")
    require(fetched.mem_id == created.mem_id, "fetched memory id mismatch")
    require(
        [result.mem_id for result in results] == [created.mem_id],
        "search results mismatch",
    )

    print(f"smoke test passed: {created.mem_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
