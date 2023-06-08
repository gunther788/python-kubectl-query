import functools
import logging

import pandas as pd

from .table import Table

logger = logging.getLogger('kubectl-query')


class Query(pd.DataFrame):
    """
    Represents the entire query and holds the result
    """

    def __init__(self, config, query_name, namespaces):
        """
        Load each resource and combine the result
        """

        data = []
        logger.debug(f"Loading data for {query_name}")

        # we can limit by namespaces if we sneak in a pseudo-table at the left
        # that lists all the namespaces we care about, the rest of the data
        # that is left-joined will be dropped if it doesn't match
        if namespaces:
            logger.debug(f"Limiting to namespace(s) {namespaces}")
            data.append(pd.DataFrame(data={"namespace": namespaces}))

        # either we've provided a query and go through all tables needed,
        # or we simply want to have one table loaded
        if query_name in config.queries:
            self.query = config.queries[query_name]
            tablenames = self.query["tables"]
        else:
            self.query = config.tables[query_name]
            tablenames = [query_name]

        # for each kind of resource, build a table and append it to the data set
        for table in tablenames:
            data.append(Table(config.client, table, **config.tables[table]))

        # zip through the data set and pd.merge them all together
        result = functools.reduce(
            lambda left, right: pd.merge(
                left,
                right,
                how="left",
            ),
            data,
        )

        logger.debug(f"Combined data for {query_name} for {len(result)} rows")

        # and we want to keep the result as a DataFrame
        super().__init__(result)

    def postprocess(self, patterns, namespaces, sort_override):
        """
        Cleanup and filtering of combined result
        """

        logger.debug("Postprocessing:")

        # drop all columns configured to be 'hidden'
        hidden = self.query.get("hidden", [])
        if hidden:
            self.drop(columns=hidden, inplace=True)
            logger.debug(f"  Dropped columns {hidden}")

        # fill the NaN's with dashes
        self.fillna("-", inplace=True)

        # sort the result
        if sort_override:
            sort_by = []
            for s in sort_override:
                if ',' in s:
                    sort_by.extend(s.split(','))
                else:
                    sort_by.append(s)
        else:
            sort_by = self.query.get("sort", [])

        if sort_by:
            try:
                self.sort_values(by=sort_by, inplace=True)
            except Exception as e:
                logger.warning(f"Could not sort by {sort_by}, error on {e}")
                pass

        # if there's a pattern or patterns, look for rows matching those patterns
        # in any column
        if patterns:
            matches = self.apply(lambda col: col.str.contains("|".join(patterns), na=False), axis=1).any(axis=1)

            # invert the selection to be able to drop those that don't match
            drop_rows = self[~matches.values].index
            self.drop(drop_rows, inplace=True)
            logger.debug(f"  Dropped {len(drop_rows)} rows that did not match {patterns}")

        return self
