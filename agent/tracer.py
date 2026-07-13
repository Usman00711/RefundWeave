"""Terminal reasoning tracer — prints a live structured log during agent execution."""
import json
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

console = Console()


def log_session_start(user_message: str):
    console.print()
    console.print(Rule("[bold magenta]🤖 AGENT SESSION STARTED[/bold magenta]", style="magenta"))
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold]User:[/bold] {user_message}")


def log_tool_call(tool_name: str, tool_input: dict):
    console.print()
    label = Text(f"  ▶  TOOL CALL: {tool_name}", style="bold cyan")
    console.print(label)
    console.print(f"  [dim]Input:[/dim] {json.dumps(tool_input, indent=4)}", style="cyan")


def log_tool_result(tool_name: str, output: str, is_denial: bool = False):
    color = "red" if is_denial else "green"
    icon = "✗" if is_denial else "✓"
    console.print(Panel(
        output,
        title=f"[bold {color}]{icon} {tool_name} result[/bold {color}]",
        border_style=color,
        expand=False,
        padding=(0, 2),
    ))


def log_agent_response(response: str):
    console.print()
    console.print(Panel(
        response,
        title="[bold white]💬 AGENT FINAL RESPONSE[/bold white]",
        border_style="white",
        padding=(0, 2),
    ))


def log_error(message: str):
    console.print()
    console.print(Panel(
        message,
        title="[bold red]⚠ ERROR / RETRY[/bold red]",
        border_style="red",
        padding=(0, 2),
    ))


def log_session_end():
    console.print()
    console.print(Rule("[dim]session complete[/dim]", style="dim"))
    console.print()
