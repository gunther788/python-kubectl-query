import itertools
import logging

import pandas as pd

logger = logging.getLogger('kubectl-query')


class Table(pd.DataFrame):
    """
    Akin to running a
      kubectl get <kind> -A -o json
    and apply the various precompiled paths across the resulting items

    If path searches return multiple items, unroll the list to produce
    multiple records
    """

    def __init__(self, client, table, api_version, kind, fields, **kwargs):
        """
        Table is really just a fancy constructor for a DataFrame that stores
        the result of an API call in table format... the magic lies within
        the fact that json path queries that result in multiple matches
        trigger multiple rows to be created, so we can treat each data set
        independently when joining other tables
        """

        def product_dict(**kwargs):
            """
            Unroll the combinations, may even be within a column if
            subqueries were used
            """
            keys = kwargs.keys()
            for instance in itertools.product(*kwargs.values()):
                values = {}
                for field, value in dict(zip(keys, instance)).items():
                    if isinstance(value, dict):
                        for subfield, subvalue in value.items():
                            values[subfield] = str(subvalue)
                    else:
                        values[field] = str(value)
                yield values

        # get all resources, all namespaces
        resource = client.resources.get(api_version=api_version, kind=kind)
        items = []

        for entry in resource.get().items:
            # extract fields by going through all paths requested
            item = {}
            for field, path in fields.items():
                if isinstance(path, dict):
                    subitem = {}
                    for subfield, subpath in path.items():
                        subitem[subfield] = [match.value for match in subpath.find(entry)]

                    # dict of lists to list of dicts
                    item[field] = [dict(zip(subitem, i)) for i in zip(*subitem.values())]

                elif isinstance(path, list):
                    item[field] = [str(match.value) for match in path[0].find(entry)]
                    for f in path[1:]:
                        item[field] = [f(v) for v in item[field]]

                else:
                    item[field] = [str(match.value) for match in path.find(entry)]

            # expand the result and add to table
            items.extend(product_dict(**item))

        logger.debug(f"  Loaded {len(items)} {table} ({kind})")

        # throw the resulting items into a DataFrame
        super().__init__(items)
