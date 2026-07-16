"""Agent command entry points and adapter runtime."""


def build_parser():
    from payskills_runtime.agent.cli import build_parser as _build_parser

    return _build_parser()


def main(argv=None) -> int:
    from payskills_runtime.agent.cli import main as _main

    return _main(argv)
