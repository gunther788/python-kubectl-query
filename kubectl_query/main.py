import logging

import click
import os.path
from colors import color
from tabulate import tabulate

from .client import Client
from .config import Config
from .query import Query

logger = logging.getLogger('kubectl-query')
logging.basicConfig(format="# %(levelname)s: %(message)s")

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.command(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-v",
    "--verbose",
    count=True,
)
@click.option(
    "-c",
    "--config",
    "configpaths",
    multiple=True,
    help="Provide config files or dirs containing table and query definitions",
)
@click.option(
    "-p",
    "--pattern",
    "patterns",
    multiple=True,
    help="""
    Limit output to rows containing TEXT, may be provided multiple times
    """,
)
@click.option(
    "-f",
    "--filter",
    "filters",
    multiple=True,
    help="""
    With A=B, Limit output to rows with value ~ B for column A, if provided
    multiple times, the result is further reduced
    """,
)
@click.option(
    "-n",
    "--namespace",
    "namespaces",
    default=None,
    multiple=True,
    help="""
    Limit output to namespace(s), may be provided multiple times
    """,
)
@click.option(
    "--context",
    "--contexts",
    "contexts",
    default=None,
    multiple=True,
    help="""
    Override the Kubernetes context, may be provided multiple times, or "all"
    """,
)
@click.option(
    "-o",
    "--tablefmt",
    default="color",
    help="""
    Table format to pass on to
    https://github.com/astanin/python-tabulate#table-format,
    default `color` that is `plain` with custom colored output
    """,
)
@click.option(
    "-s",
    "--sort",
    "sort_override",
    multiple=True,
    help="""
    Select field(s) to sort by, may be provided multiple times
    """,
)
@click.option(
    "-C",
    "--columns",
    "list_columns",
    multiple=True,
    help="""
    Select the column(s) to show, may be provided multiple times
    """,
)
@click.option(
    "-H",
    "--hide",
    "hide_columns",
    multiple=True,
    help="""
    Select the column(s) to hide, may be provided multiple times
    """,
)
@click.option(
    "-l",
    "--list",
    "list_available",
    count=True,
    help="""
    Show available tables, queries and bundles
    """,
)
@click.option(
    "-I",
    "--include",
    "include",
    default=[],
    multiple=True,
    help="""
    Include directory with yaml files
    """,
)
@click.argument("args", nargs=-1)
# pylint: disable=too-many-arguments
def main(
    verbose,
    configpaths,
    patterns,
    filters,
    namespaces,
    contexts,
    tablefmt,
    sort_override,
    hide_columns,
    list_columns,
    list_available,
    include,
    args,
):
    """
    Query the required resources and save the results into DataFrames,
    combine the results using Pandas' merge, optionally do some post-
    processing and cleanup and pretty-print the output.
    """

    # set up logging
    if verbose >= 2:
        logger.setLevel(logging.DEBUG)
    elif verbose >= 1:
        logger.setLevel(logging.INFO)

    patterns = list(patterns)
    include = [os.path.expanduser(path) for path in include]
    logger.debug("Options:")
    logger.debug(f"  Config in {configpaths}")
    logger.debug(f"  Contexts set to {contexts}")
    logger.debug(f"  Patterns set to {patterns}")
    logger.debug(f"  Filters set to {filters}")
    logger.debug(f"  Table format is {tablefmt}")
    logger.debug(f"  Include is {include}")

    # shortcuts for help pages
    if list_available:
        args = ['list']
    elif not args:
        main.main(["--help"])

    # prepare the Kubernetes client with various contexts
    client = Client(list(contexts))

    # load the configuration file into our internal structure and
    # amend the client with new contexts if needed
    config = Config(configpaths, client)

    # initialize and process the config data according to what we want to query
    config.init_config(args, patterns)

    output = []

    def render(result, tablefmt):
        """
        Turn dataframe into a table, by default colorized
        """

        # colorize the output
        if tablefmt == "color":
            colors = ["cyan", "green", "magenta", "white", "yellow"] * 3
            for column, columncolor in zip(result.columns.values, colors):
                # pylint: disable=cell-var-from-loop
                result[column] = result[column].map(lambda x: color(x, columncolor))

        return tabulate(
            result,
            tablefmt=tablefmt.replace("color", "plain"),
            stralign="left",
            showindex=False,
            headers=[h.upper() for h in result.columns],
        )

    for arg in config.show:
        # load all data
        result = Query(client, config, include, arg)
        result.postprocess(
            patterns,
            filters or config.filters,
            namespaces or config.namespaces,
            sort_override,
            hide_columns,
            list_columns,
        )
        if not len(result.index):
            continue
        output.append(render(result, tablefmt))

    if output:
        print("\n\n".join(output))
    else:
        logger.warning(f"Could not find any data for {config.show} with patterns {patterns}")


if __name__ == '__main__':
    main()
