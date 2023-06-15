import ipaddress  # noqa: F401
import itertools
import logging

import pandas as pd
from kubernetes.dynamic.resource import ResourceField

logger = logging.getLogger('kubectl-query')


class Table(pd.DataFrame):
    """
    Akin to running a
      kubectl get <kind> -A -o json
    and apply the various precompiled paths across the resulting items

    If path searches return multiple items, unroll the list to produce
    multiple records
    """

    def __init__(self, client, clustercontext, table, api_version, kind, fields, **kwargs):
        """
        Table is really just a fancy constructor for a DataFrame that stores
        the result of an API call in table format... the magic lies within
        the fact that json path queries that result in multiple matches
        trigger multiple rows to be created, so we can treat each data set
        independently when joining other tables
        """

        def format_list(value):
            if isinstance(value, list):
                return ",".join(value)
            else:
                return str(value)

        def format_match(value):
            if value.operator == 'In':
                return f"{value.key} = {format_list(value.values)}"
            elif value.operator == 'NotIn':
                return f"{value.key} != {format_list(value.values)}"
            else:
                return f"{value.key} {value.operator.lower()}"

        def format_value(value):
            if isinstance(value, ResourceField):
                if value.matchExpressions:
                    return ' & '.join([format_match(v) for v in value.matchExpressions])
                if value.matchFields:
                    return ' & '.join([format_match(v) for v in value.matchFields])
                if value.effect:
                    return f"{value.key}={value.value}:{value.effect}"

            return str(value)

        def extract_values(field, path, entry):
            """
            Fields can be defined as json paths, or json paths to be
            processed with lambda functions (defined as lists) or they
            are defined as a dict with subfields to be extracted, or
            a combination of the above.

            Returns a dict that can be merged into the table.
            """
            item = {}

            if isinstance(path, dict):
                subitem = {}
                for subfield, subpath in path.items():
                    subitem[subfield] = [format_value(match.value) for match in subpath.find(entry)] or ['<none>']

                # dict of lists to list of dicts
                item[field] = [dict(zip(subitem, i)) for i in zip(*subitem.values())]

            elif isinstance(path, list):
                item[field] = [format_value(match.value) for match in path[0].find(entry)]
                for f in path[1:]:
                    item[field] = [f(v) for v in item[field]]

            else:
                item[field] = [format_value(match.value) for match in path.find(entry)] or ['<none>']

            return item

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
                            values[subfield] = subvalue
                    else:
                        values[field] = value
                yield values

        # get all resources, all namespaces
        items = []

        try:
            resource = client.resources.get(api_version=api_version, kind=kind)

            for entry in resource.get().items:
                # extract fields by going through all paths requested
                item = {'context': [clustercontext]}
                for field, path in fields.items():
                    item.update(extract_values(field, path, entry))

                # expand the result and add to table
                items.extend(product_dict(**item))

        except Exception as e:
            logger.warning(f"Failed to get {kind}, {e}")
            pass

        logger.debug(f"  Loaded {len(items)} {table} ({kind})")

        # throw the resulting items into a DataFrame
        super().__init__(items)
