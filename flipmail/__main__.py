"""Enable ``python -m flipmail`` to invoke the CLI (the installed command is ``mailbox``)."""

from flipmail.cli import cli

if __name__ == "__main__":
    cli()
