import functools
import logging

import pandas as pd

from .table import Table

logger = logging.getLogger('kubectl-query')


class Query(pd.DataFrame):
    """
    Represents the entire query and holds the result
    """

    def __init__(self, client, config, query_name):
        """
        Load each resource and combine the result
        """

        data = []
        logger.debug(f"Loading data for '{query_name}'")

        # either we've provided a query and go through all tables needed,
        # or we simply want to have one table loaded
        if query_name in config.queries:
            self.query = config.queries[query_name]
            tablenames = self.query.get("tables", [])
        elif query_name in config.tables:
            self.query = config.tables[query_name]
            tablenames = [query_name]

        # for showing the internal state
        if query_name in ['tables', 'queries', 'bundles']:
            data = [config.as_table(query_name)]
        else:
            # for each kind of resource, build a table and append it to the data set
            for table in tablenames:
                data.append(Table(client, table, **config.tables[table]))

        # zip through the data set and pd.merge them all together
        try:
            result = functools.reduce(
                lambda left, right: pd.merge(
                    left,
                    right,
                    how="left",
                ),
                data,
            )
        except Exception as e:
            logger.critical(f"Could not join {tablenames} together: {e}")
            result = []
            pass

        logger.debug(f"Combined data for {query_name} for {len(result)} rows")

        # and we want to keep the result as a DataFrame
        super().__init__(result)

    def postprocess(self, patterns, filters, namespaces, sort_override, list_columns):
        """
        Cleanup and filtering of combined result
        """

        logger.debug("Postprocessing:")

        # drop rows that have no namespace or the namespace isn't in the list
        if namespaces and 'namespace' in self.columns:
            logger.debug(f"Limiting to namespace(s) {namespaces}")
            matches = self.loc[self['namespace'].isin(namespaces)]
            drop_rows = self.index.difference(matches.index)
            self.drop(drop_rows, inplace=True)

        if filters:
            for k, v in [f.split('=') for f in filters]:
                k = k.lower()
                logger.debug(f"Filtering on '{k}' with pattern '.*{v}.*'")
                matches = self[k].str.match(f".*{v}.*")
                matches.fillna(False, inplace=True)

                # invert the selection to be able to drop those that don't match
                if any(matches.values):
                    drop_rows = self[~matches.values].index
                    self.drop(drop_rows, inplace=True)
                    logger.debug(f"  Dropped {len(drop_rows)} rows that did not match {patterns}")

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

        # select a possible subset of columns
        hide = []
        if list_columns:
            limit_columns = []
            for c in list_columns:
                if ',' in c:
                    limit_columns.extend(c.lower().split(','))
                else:
                    limit_columns.append(c.lower())

            logger.debug(f"Limiting columns to {limit_columns}")

            for c in self.columns:
                if c not in limit_columns:
                    hide.append(c)

        # drop all columns configured to be 'hide'
        hide.extend(self.query.get("hide", []))
        if hide:
            self.drop(columns=hide, inplace=True)
            logger.debug(f"  Dropped columns {hide}")

        return self
