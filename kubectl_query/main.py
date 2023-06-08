import logging

import click
from colors import color
from tabulate import tabulate

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
    help="Limit output to rows containing TEXT, may be provided multiple times",
)
@click.option(
    "-n",
    "--namespace",
    "namespaces",
    multiple=True,
    help="""
    Limit output to namespace(s), may be provided multiple times
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
    "-l",
    "--list",
    "list_available",
    count=True,
    help="""
    Show available tables and queries
    """,
)
@click.argument("queries", nargs=-1)
# pylint: disable=too-many-arguments
def main(
    verbose,
    configpaths,
    patterns,
    namespaces,
    tablefmt,
    sort_override,
    list_columns,
    list_available,
    queries,
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

    logger.debug("Options:")
    logger.debug(f"  Config in {configpaths}")
    logger.debug(f"  Patterns set to {patterns}")
    logger.debug(f"  Table format is {tablefmt}")

    # load the configuration file into our internal structure
    config = Config(configpaths)
    queries = config.check_queries(queries)

    logger.debug("  Config loaded, on to checking")

    if list_available:
        queries = ['list']
    elif not queries:
        main.main(["--help"])

    for i, query_name in enumerate(queries):
        if i > 0:
            print()

        # load all required data
        result = Query(config, query_name)

        # cleanup and filter
        result.postprocess(patterns, namespaces, sort_override, list_columns)

        # colorize the output
        if tablefmt == "color":
            colors = ["cyan", "green", "magenta", "white", "yellow"] * 3
            for column, columncolor in zip(result.columns.values, colors):
                # pylint: disable=cell-var-from-loop
                result[column] = result[column].map(lambda x: color(x, columncolor))

        print(
            tabulate(
                result,
                tablefmt=tablefmt.replace("color", "plain"),
                stralign="left",
                showindex=False,
                headers=[h.upper() for h in result.columns],
            )
        )


if __name__ == '__main__':
    main()
