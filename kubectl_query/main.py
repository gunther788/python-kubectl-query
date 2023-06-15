import logging

import click
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
    filters,
    namespaces,
    contexts,
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
    logger.debug(f"  Contexts set to {contexts}")
    logger.debug(f"  Patterns set to {patterns}")
    logger.debug(f"  Filters set to {filters}")
    logger.debug(f"  Table format is {tablefmt}")

    # shortcuts for help pages
    if list_available or 'list' in queries:
        queries = ['tables', 'queries']
    elif not queries:
        main.main(["--help"])

    # prepare the Kubernetes client with various contexts
    client = Client(list(contexts))

    # load the configuration file into our internal structure and
    # amend the client with new contexts if needed
    config = Config(configpaths, client)
    (queries, patterns) = config.check_queries(queries, patterns)
    tables = config.init_queries(queries)
    config.init_tables(tables + queries)

    logger.debug("  Config loaded, on to checking")

    for i, query_name in enumerate(queries):
        if i > 0:
            print()

        # load all data
        result = Query(client, config, query_name)

        # cleanup and filter
        result.postprocess(patterns, filters, namespaces, sort_override, list_columns)

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
