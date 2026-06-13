"""
Application entry point.

Run with:
    python run.py --env dev
    python run.py --env prod
"""

import click
from app import create_app


@click.command()
@click.option(
    "--env",
    default="dev",
    show_default=True,
    help="Runtime environment (dev|prod)",
)
def cli(env: str) -> None:
    app = create_app(env)
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    cli()
