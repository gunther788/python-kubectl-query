import itertools
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class Table(pd.DataFrame):
    """
    Akin to running a
      kubectl get <kind> -A -o json
    and apply the various precompiled paths across the resulting items

    If path searches return multiple items, unroll the list to produce
    multiple records
    """

    def __init__(self, client, api_version, kind, fields, **_):
        """
        Table is really just a fancy constructor for a DataFrame that stores
        the result of an API call in table format... the magic lies within
        the fact that json path queries that result in multiple matches
        trigger multiple rows to be created, so we can treat each data set
        independently when joining other tables
        """

        def product_dict(**kwargs):
            """
            Gem found at
            https://stackoverflow.com/questions/5228158
            """
            keys = kwargs.keys()
            for instance in itertools.product(*kwargs.values()):
                yield dict(zip(keys, instance))

        # get all resources, all namespaces
        resource = client.resources.get(api_version=api_version, kind=kind)
        items = []
        for entry in resource.get().items:
            # extract fields by going through all paths requested
            item = {}
            for field, path in fields.items():
                item[field] = [str(match.value) for match in path.find(entry)]

            # expand the result and add to table
            items.extend(product_dict(**item))

        logger.debug(f"  Loaded {len(items)} {kind}")

        # throw the resulting items into a DataFrame
        super().__init__(items)
