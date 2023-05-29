import logging
import sys
import click
from tabulate import tabulate
from colors import color

from .config import Config
from .query import Query


logger = logging.getLogger(__name__)
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
    "configfile",
    default=f"{__file__}.yaml",
    help=f"Provide a config file containing tables and queries, default {__file__}.yaml",
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
    Limit output to namespace(s), may be provided multiple times. Do note that
    if the first table/query does not contain namespaces, the merge will fail.
    """,
)
@click.option(
    "-o",
    "--tablefmt",
    default="color",
    help="""
    Table format to pass on to https://github.com/astanin/python-tabulate#table-format,
    default `color` that is `plain` with custom colored output
    """,
)
@click.argument("queries", nargs=-1)
# pylint: disable=too-many-arguments
def main(
    verbose,
    configfile,
    patterns,
    namespaces,
    tablefmt,
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
    logger.debug(f"  Config in {configfile}")
    logger.debug(f"  Patterns set to {patterns}")
    logger.debug(f"  Table format is {tablefmt}")

    # load the configuration file into our internal structure
    config = Config(configfile)
    queries = config.check_queries(queries)

    if not queries:
        for message in config.get_available_queries():
            print(message)
        main.main(["--help"])

    for query_name in queries:
        # load all required data
        result = Query(config, query_name, namespaces)

        # cleanup and filter
        result.postprocess(patterns)

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
    sys.exit(main())
