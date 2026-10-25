
import re
import typer
from rich.console import Console
from rich.prompt import IntPrompt

from commit.git_utils import is_git_repo, get_diff
from commit.llm import generate_commit_messages

app = typer.Typer()
console = Console()


@app.command()
def check():
    """Generate and select a Git commit message."""

    if not is_git_repo():
        console.print("[red]This folder is not a Git repository.[/red]")
        raise typer.Exit(code=1)

    try:
        diff = get_diff(mode="both")

        if not diff:
            console.print("[yellow]No code changes found.[/yellow]")
            return

        console.print("[bold]Generating commit messages...[/bold]")
        result = generate_commit_messages(diff)

        matches = re.findall(
            r"(?m)^\s*(\d+)\.\s*`?(.+?)(?:`)?\s*$",
            result
        )

        suggestions = []
        for _, message in matches:
            message = message.strip().strip("`")
            if message:
                suggestions.append(message)

        if not suggestions:
            console.print(
                "[red]The AI returned no usable suggestions.[/red]"
            )
            console.print(result)
            return

        console.print("\n[bold green]Suggested commit messages:[/bold green]")

        for index, message in enumerate(suggestions, start=1):
            console.print(f"{index}. {message}")

        choice = IntPrompt.ask(
            "Choose a suggestion number, or enter 0 to cancel",
            default=0
        )

        if choice == 0:
            console.print(
                "[yellow]Cancelled. No commit was created.[/yellow]"
            )

        elif 1 <= choice <= len(suggestions):
            console.print("\n[bold]Selected commit message:[/bold]")
            console.print(suggestions[choice - 1])
            console.print("[dim]No Git commit has been created yet.[/dim]")

        else:
            console.print("[red]Invalid selection.[/red]")

    except (RuntimeError, ValueError) as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(code=1)

    except Exception as error:
        console.print(
            f"[red]Could not contact the local AI model: {error}[/red]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
