import glob
import importlib.resources
import ipaddress  # noqa: F401
import logging
import os

import pandas as pd
import yaml
from jsonpath_ng.ext import parse

logger = logging.getLogger('kubectl-query')


class Config:
    """
    Represents the config file and does sanity checking of the input
    """

    def __init__(self, configpaths, client):
        """
        Parse the configuration files or directories and compile the
        JSON paths needed to select fields later on
        """

        self.config = {'tables': {}, 'queries': {}}

        built_in = importlib.resources.files(__package__).joinpath('config')
        configpaths = (built_in,) + configpaths

        for configpath in configpaths:
            if os.path.isfile(configpath):
                self.merge_config(configpath)
            elif os.path.isdir(configpath):
                for configfile in glob.glob(f"{configpath}/*.yaml"):
                    self.merge_config(configfile)
            else:
                logger.warning(f"Don't know what to do with '{configpath}'")

        logger.debug("Compiling configs:")
        self.init_tables(client.default_contexts)
        self.init_queries()

    def merge_config(self, configpath):
        """
        Snarf in one more yaml file and return the dict, skip
        with a warning if it can't be parsed
        """
        logger.debug(f"Reading {configpath}")
        with open(configpath, "r", encoding="utf-8") as stream:
            try:
                new = yaml.safe_load(stream)
                if 'tables' not in new and 'queries' not in new:
                    logger.warning(f"{configpath} contains neither tables nor queries")

            except yaml.YAMLError as exception:
                logger.warning(exception)
                new = {}

        filename = os.path.basename(configpath)
        for table, prop in new.get('tables', {}).items():
            prop.setdefault('file', filename)
        for query, prop in new.get('queries', {}).items():
            prop.setdefault('file', filename)

        self.config['tables'] = {**self.config['tables'], **new.get('tables', {})}
        self.config['queries'] = {**self.config['queries'], **new.get('queries', {})}

    def init_tables(self, default_contexts):
        """
        Process tables
        """

        for table, prop in self.config.get("tables", {}).items():
            logger.debug(f"  Loading config for table '{table}'")
            prop.setdefault('contexts', default_contexts)

            # for fields we need to compile the path
            for field, path in prop.get("fields", {}).items():
                if isinstance(path, dict):
                    for subfield, subpath in path.items():
                        prop["fields"][field][subfield] = parse(subpath)

                elif isinstance(path, list):
                    prop["fields"][field] = [parse(path[0])] + [eval(f) for f in path[1:]]

                elif isinstance(path, str):
                    prop["fields"][field] = parse(path)

    def init_queries(self):
        """
        Process queries
        """

        for query, prop in self.config.get("queries", {}).items():
            logger.debug(f"  Loading config for query '{query}'")
            for table in prop.get("tables", []):
                if table not in self.config['tables']:
                    logger.warning(f"Query '{query}' makes use of an unknown table '{table}'")

    def unaliases(self):
        """
        Build a dict of all aliases for tables and queries
        """

        unalias = {}
        for name, prop in list(self.tables.items()) + list(self.queries.items()):
            for alias in prop.get('aliases', []):
                unalias[alias] = name

        return unalias

    def check_queries(self, iq, patterns):
        """
        Make sure that all requested queries are defined, otherwise show
        the user what we have
        """

        available = list(self.queries.keys()) + list(self.tables.keys())
        unalias = self.unaliases()

        oq = []
        for query in iq:
            if query in unalias:
                oq.append(unalias[query])
            else:
                oq.append(query)

        if all(query in available for query in oq):
            return (oq, patterns)

        errors = list(filter(lambda query: query not in available, oq))

        oq = []
        for error in errors:
            matches = list(filter(lambda a: error in a, available))
            if len(matches) == 1:
                oq.extend(matches)
            else:
                return (['tables', 'queries'], iq + patterns)

        return (oq, patterns)

    @property
    def tables(self):
        """All available tables"""
        return self.config["tables"] or {}

    @property
    def queries(self):
        """All available queries"""
        return self.config["queries"] or {}

    def as_table(self, kind):
        """
        Take the internal config and render it as table for help
        """

        available = []
        for name, prop in sorted(self.config[kind].items()):
            available.append(
                {
                    'name': name,
                    'aliases': ', '.join(prop.get('aliases', [])) or None,
                    'file': prop.get('file', ''),
                    'contexts': ', '.join(prop.get('contexts', [])),
                    'references': ', '.join(prop.get('tables', [])) or None,
                    'note': prop.get('note', ""),
                }
            )

        return pd.DataFrame(available)
