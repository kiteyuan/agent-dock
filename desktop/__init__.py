"""Host desktop pet UI (launched with Runtime on the same machine)."""

__all__ = ["main"]


def main() -> None:
    from desktop.serve import main as serve_main

    serve_main()
