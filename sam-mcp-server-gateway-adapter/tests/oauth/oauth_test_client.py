#!/usr/bin/env python3
"""
OAuth Test Client for MCP Server Gateway Adapter.

Interactive CLI tool to test OAuth endpoints and flows.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import TestConfig
from .test_scenarios import (
    ClientRegistrationTest,
    CompleteOAuthFlowTest,
    MetadataDiscoveryTest,
    PKCEInvalidVerifierTest,
    RefreshTokenTest,
    TestResult,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

console = Console()


class OAuthTestClient:
    """Main OAuth test client."""

    def __init__(self, config: TestConfig):
        """
        Initialize test client.

        Args:
            config: Test configuration
        """
        self.config = config
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
        self.test_results: List[TestResult] = []

    async def cleanup(self):
        """Clean up resources."""
        await self.client.aclose()

    def display_header(self):
        """Display CLI header."""
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]MCP OAuth Test Client[/bold cyan]\n"
                f"[dim]Testing: {self.config.mcp_server_url}[/dim]\n"
                f"[dim]Auth Proxy: {self.config.auth_proxy_url}[/dim]",
                border_style="cyan",
            )
        )
        console.print()

    def display_menu(self):
        """Display interactive menu."""
        console.print("[bold]Available Tests:[/bold]\n", style="cyan")

        tests = [
            ("1", "Run Complete OAuth Flow", "Full authorization code grant with PKCE"),
            ("2", "Test OAuth Metadata Discovery", "RFC 8414 metadata endpoint"),
            ("3", "Test Dynamic Client Registration", "RFC 7591 client registration"),
            ("4", "Test Refresh Token Flow", "Expect failure - not implemented"),
            ("5", "Test PKCE Validation", "Invalid verifier test"),
            ("", "", ""),
            ("a", "Run All Tests", "Execute all test scenarios"),
            ("r", "View Test Results", "Display results from previous tests"),
            ("e", "Export Results", "Save results to JSON/Markdown"),
            ("q", "Quit", "Exit the test client"),
        ]

        for num, name, desc in tests:
            if not num:
                console.print()
                continue
            console.print(f"  [{num}] {name}", style="bold green")
            console.print(f"      [dim]{desc}[/dim]")

        console.print()

    async def run_test(self, test_name: str) -> TestResult:
        """
        Run a specific test scenario.

        Args:
            test_name: Name of test to run

        Returns:
            Test result
        """
        test_map = {
            "metadata": MetadataDiscoveryTest,
            "registration": ClientRegistrationTest,
            "complete-flow": CompleteOAuthFlowTest,
            "refresh": RefreshTokenTest,
            "pkce-invalid": PKCEInvalidVerifierTest,
        }

        test_class = test_map.get(test_name)
        if not test_class:
            raise ValueError(f"Unknown test: {test_name}")

        test = test_class(self.client, self.config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Running {test_class.__name__}...", total=None)
            result = await test.run()
            progress.update(task, completed=True)

        return result

    def display_result(self, result: TestResult):
        """
        Display test result.

        Args:
            result: Test result to display
        """
        # Overall status with color
        status_colors = {
            "PASS": "green",
            "FAIL": "red",
            "SKIP": "yellow",
            "INFO": "blue",
        }
        status_color = status_colors.get(result.overall_status, "white")

        console.print()
        console.print(
            Panel.fit(
                f"[bold]{result.name}[/bold]\n"
                f"Status: [{status_color}]{result.overall_status}[/{status_color}]\n"
                f"Duration: {result.duration:.2f}s",
                border_style=status_color,
            )
        )

        # Display steps
        if result.steps:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Step", style="cyan")
            table.add_column("Status", style="white")
            table.add_column("Details", style="dim")

            for step in result.steps:
                step_color = status_colors.get(step.status, "white")
                details_str = ""
                if step.details:
                    if isinstance(step.details, dict):
                        # Truncate long dictionaries
                        details_str = str(step.details)[:100]
                        if len(str(step.details)) > 100:
                            details_str += "..."
                    else:
                        details_str = str(step.details)[:100]

                table.add_row(
                    step.name,
                    f"[{step_color}]{step.status}[/{step_color}]",
                    details_str,
                )

            console.print(table)

        if result.error:
            console.print(f"\n[red]Error: {result.error}[/red]")

        console.print()

    async def run_all_tests(self):
        """Run all test scenarios."""
        console.print("[bold cyan]Running All Tests[/bold cyan]\n")

        test_sequence = [
            ("metadata", "OAuth Metadata Discovery"),
            ("registration", "Dynamic Client Registration"),
            ("complete-flow", "Complete OAuth Flow"),
            ("refresh", "Refresh Token Flow"),
            ("pkce-invalid", "PKCE Invalid Verifier"),
        ]

        self.test_results = []

        for test_name, test_label in test_sequence:
            console.print(f"[bold]Running: {test_label}[/bold]")
            try:
                result = await self.run_test(test_name)
                self.test_results.append(result)
                self.display_result(result)
            except Exception as e:
                log.exception(f"Test {test_name} failed with exception")
                console.print(f"[red]Test failed: {str(e)}[/red]\n")

        self.display_summary()

    def display_summary(self):
        """Display test summary."""
        if not self.test_results:
            console.print("[yellow]No test results to display[/yellow]")
            return

        passed = sum(1 for r in self.test_results if r.overall_status == "PASS")
        failed = sum(1 for r in self.test_results if r.overall_status == "FAIL")
        total = len(self.test_results)

        console.print()
        console.print(
            Panel.fit(
                f"[bold]Test Summary[/bold]\n\n"
                f"Total:  {total}\n"
                f"[green]Passed: {passed}[/green]\n"
                f"[red]Failed: {failed}[/red]\n"
                f"Duration: {sum(r.duration for r in self.test_results):.2f}s",
                border_style="cyan",
                title="Summary",
            )
        )
        console.print()

    def export_results(self, format: str = "json"):
        """
        Export test results to file.

        Args:
            format: Export format ('json' or 'markdown')
        """
        if not self.test_results:
            console.print("[yellow]No results to export[/yellow]")
            return

        # Create results directory
        results_dir = Path(self.config.results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            filename = results_dir / f"oauth_test_{timestamp}.json"
            data = {
                "timestamp": datetime.now().isoformat(),
                "config": self.config.model_dump_safe(),
                "results": [
                    {
                        "name": r.name,
                        "status": r.overall_status,
                        "duration": r.duration,
                        "error": r.error,
                        "steps": [
                            {
                                "name": s.name,
                                "status": s.status,
                                "details": str(s.details) if s.details else None,
                            }
                            for s in r.steps
                        ],
                    }
                    for r in self.test_results
                ],
                "summary": {
                    "total": len(self.test_results),
                    "passed": sum(1 for r in self.test_results if r.overall_status == "PASS"),
                    "failed": sum(1 for r in self.test_results if r.overall_status == "FAIL"),
                },
            }

            with open(filename, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"[green]Results exported to: {filename}[/green]")

        elif format == "markdown":
            filename = results_dir / f"oauth_test_{timestamp}.md"
            with open(filename, "w") as f:
                f.write("# OAuth Test Results\n\n")
                f.write(f"**Date**: {datetime.now().isoformat()}\n\n")
                f.write(f"**MCP Server**: {self.config.mcp_server_url}\n\n")
                f.write("## Summary\n\n")
                f.write(f"- Total Tests: {len(self.test_results)}\n")
                f.write(f"- Passed: {sum(1 for r in self.test_results if r.overall_status == 'PASS')}\n")
                f.write(f"- Failed: {sum(1 for r in self.test_results if r.overall_status == 'FAIL')}\n\n")

                f.write("## Test Details\n\n")
                for result in self.test_results:
                    status_emoji = "✅" if result.overall_status == "PASS" else "❌"
                    f.write(f"### {status_emoji} {result.name} ({result.duration:.2f}s)\n\n")
                    f.write(f"**Status**: {result.overall_status}\n\n")

                    if result.steps:
                        f.write("**Steps**:\n\n")
                        for step in result.steps:
                            step_emoji = {
                                "PASS": "✓",
                                "FAIL": "✗",
                                "INFO": "ℹ",
                                "SKIP": "⊘",
                            }.get(step.status, "•")
                            f.write(f"- {step_emoji} {step.name}: {step.status}\n")

                    if result.error:
                        f.write(f"\n**Error**: {result.error}\n")

                    f.write("\n")

            console.print(f"[green]Results exported to: {filename}[/green]")

    async def run_interactive(self):
        """Run interactive CLI menu."""
        self.display_header()

        while True:
            self.display_menu()
            choice = console.input("[bold cyan]Select option:[/bold cyan] ").strip().lower()

            if choice == "q":
                console.print("[yellow]Exiting...[/yellow]")
                break
            elif choice == "1":
                result = await self.run_test("complete-flow")
                self.test_results.append(result)
                self.display_result(result)
            elif choice == "2":
                result = await self.run_test("metadata")
                self.test_results.append(result)
                self.display_result(result)
            elif choice == "3":
                result = await self.run_test("registration")
                self.test_results.append(result)
                self.display_result(result)
            elif choice == "4":
                result = await self.run_test("refresh")
                self.test_results.append(result)
                self.display_result(result)
            elif choice == "5":
                result = await self.run_test("pkce-invalid")
                self.test_results.append(result)
                self.display_result(result)
            elif choice == "a":
                await self.run_all_tests()
            elif choice == "r":
                for result in self.test_results:
                    self.display_result(result)
                self.display_summary()
            elif choice == "e":
                self.export_results("json")
                self.export_results("markdown")
            else:
                console.print("[red]Invalid option[/red]")

            console.input("\n[dim]Press Enter to continue...[/dim]")
            console.clear()
            self.display_header()


@click.command()
@click.option(
    "--mcp-url",
    default="http://localhost:8090",
    help="MCP server URL",
)
@click.option(
    "--auth-url",
    default="http://localhost:8050",
    help="Auth proxy URL",
)
@click.option(
    "--callback-port",
    default=8888,
    type=int,
    help="Callback server port",
)
@click.option(
    "--test",
    type=click.Choice(["metadata", "registration", "complete-flow", "refresh", "pkce-invalid"]),
    help="Run specific test",
)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    help="Run all tests",
)
@click.option(
    "--export",
    type=click.Choice(["json", "markdown", "both"]),
    help="Export results",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def main(
    mcp_url: str,
    auth_url: str,
    callback_port: int,
    test: Optional[str],
    run_all: bool,
    export: Optional[str],
    verbose: bool,
):
    """OAuth Test Client for MCP Server Gateway Adapter."""

    # Configure logging
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create configuration
    config = TestConfig(
        mcp_server_url=mcp_url,
        auth_proxy_url=auth_url,
        callback_port=callback_port,
        verbose=verbose,
    )

    # Create client
    client = OAuthTestClient(config)

    async def run():
        try:
            if test:
                # Run specific test
                result = await client.run_test(test)
                client.test_results.append(result)
                client.display_result(result)
            elif run_all:
                # Run all tests
                await client.run_all_tests()
            else:
                # Interactive mode
                await client.run_interactive()

            # Export if requested
            if export:
                if export == "both":
                    client.export_results("json")
                    client.export_results("markdown")
                else:
                    client.export_results(export)

        finally:
            await client.cleanup()

    asyncio.run(run())


if __name__ == "__main__":
    main()
