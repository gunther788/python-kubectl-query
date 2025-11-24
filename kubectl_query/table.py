import ast  # noqa: F401
import glob
import ipaddress  # noqa: F401
import itertools
import logging

import pandas as pd
import requests
import yaml
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

    def __init__(self, client, table, include, api, kind, fields, **kwargs):
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

                # convert to string and back to yaml
                # return yaml.dump(yaml.load(str(value), Loader=yaml.FullLoader)).rstrip()

            return str(value)

        def unroll(value):
            if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
                return value[0]
            return value

        def unrange(value):
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            value = ast.literal_eval(value)
            ret = value

            if isinstance(value, dict):
                if 'start' in value and 'stop' in value:
                    ret = []
                    addr = ipaddress.IPv4Address(value['start'])
                    stop = ipaddress.IPv4Address(value['stop'])
                    while addr <= stop:
                        ret.append(str(addr))
                        addr = addr + 1

                elif 'cidr' in value:
                    logger.debug(f"Unroll {value}")
                    ret = [str(addr) for addr in ipaddress.IPv4Network(value['cidr'])]
                    logger.debug(f"   got {ret}")

            return ret

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
                    if f != 'unroll' and f != 'unrange':
                        item[field] = [f(v) for v in item[field]]

                if 'unroll' in path:
                    item[field] = unroll(item[field])

                if 'unrange' in path:
                    item[field] = unrange(item[field])

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

        contexts = kwargs.get('contexts', [])
        logger.debug(f"Initializing table {table} with contexts {contexts}")

        # get resources, all contexts and all namespaces
        items = []

        if len(contexts) == 1:
            kwargs['no_context'] = True

        if api == 'file':

            # load data from yaml files found in the include paths
            resources = {}

            logger.debug(f'Scanning {include}')
            for path in include:
                for filename in glob.glob(f"{path}/**/*.y*ml", recursive=True):
                    logger.debug(f'Reading {filename}')
                    with open(filename) as stream:
                        try:
                            resources.update(yaml.safe_load(stream))
                        except yaml.YAMLError as e:
                            logger.warning(e)

            for entry in resources[kind]:
                item = {}

                # extract fields by going through all paths requested
                for field, path in fields.items():
                    item.update(extract_values(field, path, entry))

                # expand the result and add to table
                items.extend(product_dict(**item))

        elif api == 'url':

            # load data from an arbitrary url instead
            url = kwargs.get('url')
            try:
                r = requests.get(url, headers=kwargs.get('headers', {}))
            except Exception as e:
                logger.info(f"Could not request {url}: {e}")

            resources = yaml.safe_load(r.text)

            for entry in resources[kind]:
                item = {}

                # extract fields by going through all paths requested
                for field, path in fields.items():
                    item.update(extract_values(field, path, entry))

                # expand the result and add to table
                items.extend(product_dict(**item))

        else:

            # limit queries to namespaces
            namespaces = kwargs.get('namespaces', [])

            # for each cluster, get the data and build one long table with all the data
            for context in contexts:
                try:
                    logger.debug(f"  Loading '{table}' from '{context}'")
                    resource = client.client(context).resources.get(api_version=api, kind=kind)

                    # if the config limits us to certain namespaces, only get that data to begin with
                    entries = []
                    if namespaces:
                        for namespace in namespaces:
                            entries.extend(resource.get(namespace=namespace).items)
                    else:
                        entries = resource.get().items

                    for entry in entries:
                        if kwargs.get('no_context', False):
                            item = {}
                        else:
                            item = {'context': [context]}

                        # cilium network policies, for example, allow `specs` as a list of spec
                        specs = entry.get('specs', [entry['spec']])
                        subentry = entry

                        for spec in specs:
                            setattr(subentry, 'spec', spec)

                            # extract fields by going through all paths requested
                            for field, path in fields.items():
                                item.update(extract_values(field, path, subentry))

                            # expand the result and add to table
                            items.extend(product_dict(**item))

                except Exception as e:
                    logger.info(f"Failed to get '{kind}' from '{context}', {e}")
                    pass

        logger.debug(f"  Loaded {len(items)} {table} ({kind})")

        # throw the resulting items into a DataFrame
        super().__init__(items)
