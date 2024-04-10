import json
import sys
from typing import List, Optional

import click
from pydantic import BaseModel, Field

from codemodder import __version__
from codemodder.code_directory import DEFAULT_EXCLUDED_PATHS, DEFAULT_INCLUDED_PATHS
from codemodder.logging import OutputFormat, logger
from codemodder.registry import CodemodRegistry


class CLIArgs(BaseModel):
    """
    Data class to assist with parsing and validating CLI arguments.
    """

    directory: Optional[str] = Field(None, description="Path to find files")
    output: Optional[str] = Field(
        None,
        type=str,
        description="Name of output file to produce",
    )
    output_format: str = Field(
        "codetf",
        type=str,
        description="The format for the data output file",
    )
    dry_run: bool = Field(
        False,
        description="Do everything except make changes to files",
    )
    verbose: bool = Field(
        False,
        description="Print more to stdout",
    )
    log_format: str = Field(
        "human",
        description="The format for the log output",
    )
    project_name: Optional[str] = Field(
        None,
        description="Optional descriptive name for the project used in log output",
    )
    path_exclude: List[str] = Field(
        DEFAULT_EXCLUDED_PATHS,
        description="UNIX glob patterns to exclude",
    )
    path_include: List[str] = Field(
        DEFAULT_INCLUDED_PATHS,
        description="UNIX glob patterns to include",
    )
    max_workers: int = Field(
        1,
        description="Maximum number of workers (threads) to use",
    )
    sarif: List[str] | None = Field(
        None,
        description="Paths to SARIF files",
    )
    sonar_issues_json: List[str] | None = Field(
        None,
        description="Paths to Sonar issues JSON files",
    )
    sonar_hotspots_json: List[str] | None = Field(
        None,
        description="Paths to Sonar hotspots JSON files",
    )
    defectdojo_findings_json: List[str] | None = Field(
        None,
        description="Paths to DefectDojo's v2 Findings JSON files",
    )
    codemod_exclude: List[str] | None = Field(
        None,
        description="Codemod ID(s) to exclude",
    )
    codemod_include: List[str] | None = Field(
        None,
        description="Codemod ID(s) to include",
    )
    list: bool = Field(
        False,
        description="Print codemod names and exit",
    )
    describe: bool = Field(
        False,
        description="Print detailed codemod metadata and exit",
    )


class ClickCommandWithErrorLogging(click.Command):
    """
    Command class wrapper to handle error logging.
    """
    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except click.ClickException as err:
            click.echo(ctx.get_help())
            logger.error("CLI error: %s", err.message)
            sys.exit(3)
        except Exception as err:
            click.echo(ctx.get_help())
            logger.error("Unhandled exception: %s", err)
            sys.exit(3)


def process_csv_list(ctx, param, value):
    """
    Action to convert "a,b,c" into ["a", "b", "c"]
    """
    if value is None:
        return []
    return list(dict.fromkeys(value.split(",")))


@click.group(cls=ClickCommandWithErrorLogging)
@click.version_option(version=__version__)
@click.pass_context
@click.argument("directory", type=click.Path(), required=False)
@click.option("--output", type=str, help="Name of output file to produce")
@click.option(
    "--output-format",
    type=click.Choice(["codetf", "diff"]),
    default="codetf",
    help="The format for the data output file",
)
@click.option(
    "--dry-run", is_flag=True, help="Do everything except make changes to files"
)
@click.option("--verbose", is_flag=True, help="Print more to stdout")
@click.option(
    "--log-format",
    type=click.Choice([OutputFormat.HUMAN.value, OutputFormat.JSON.value]),
    default=OutputFormat.HUMAN.value,
    help="The format for the log output",
)
@click.option(
    "--project-name",
    help="Optional descriptive name for the project used in log output",
)
@click.option(
    "--path-exclude",
    callback=process_csv_list,
    default=DEFAULT_EXCLUDED_PATHS,
    help="Comma-separated set of UNIX glob patterns to exclude",
)
@click.option(
    "--path-include",
    callback=process_csv_list,
    default=DEFAULT_INCLUDED_PATHS,
    help="Comma-separated set of UNIX glob patterns to include",
)
@click.option(
    "--max-workers",
    type=int,
    default=1,
    help="Maximum number of workers (threads) to use for processing files in parallel",
)
@click.option(
    "--sarif",
    callback=process_csv_list,
    help="Comma-separated set of path(s) to SARIF file(s) to feed to the codemods",
)
@click.option(
    "--sonar-issues-json",
    callback=process_csv_list,
    help="Comma-separated set of path(s) to Sonar issues JSON file(s) to feed to the codemods",
)
@click.option(
    "--sonar-hotspots-json",
    callback=process_csv_list,
    help="Comma-separated set of path(s) to Sonar hotspots JSON file(s) to feed to the codemods",
)
@click.option(
    "--defectdojo-findings-json",
    callback=process_csv_list,
    help="Comma-separated set of path(s) to DefectDojo's v2 Findings JSON file(s) to feed to the codemods",
)
@click.option(
    "--codemod-exclude",
    callback=process_csv_list,
    help="Comma-separated set of codemod ID(s) to exclude",
)
@click.option(
    "--codemod-include",
    callback=process_csv_list,
    help="Comma-separated set of codemod ID(s) to include",
)
@click.option(
    "--list",
    is_flag=True,
    help="Print codemod names to stdout and exit",
)
@click.option(
    "--describe",
    is_flag=True,
    help="Print detailed codemod metadata to stdout exit",
)
def parse_args(ctx, **kwargs):
    """
    Parse CLI arguments and options using the provided context.
    """
    parsed_args = CLIArgs(**kwargs)
    codemod_registry: CodemodRegistry = ctx.obj['codemod_registry']

    if parsed_args.list:
        for codemod_id in sorted(codemod_registry.ids):
            click.echo(codemod_id)
        sys.exit(0)

    if parsed_args.describe:
        results = codemod_registry.describe_codemods(
            parsed_args.codemod_include, parsed_args.codemod_exclude
        )
        click.echo(json.dumps({"results": results}, indent=2))
        sys.exit(0)

    return parsed_args
