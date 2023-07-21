import ast  # noqa: F401
import glob
import importlib.resources
import ipaddress  # noqa: F401
import logging
import os
import sys

import pandas as pd
import yaml
from jsonpath_ng.ext import parse

logger = logging.getLogger('kubectl-query')


class Config:
    """
    Represents the config files and does sanity checking of the input
    """

    def __init__(self, configpaths, client):
        """
        Parse the configuration files or directories and compile the
        JSON paths needed to select fields later on
        """

        self.config = {'tables': {}, 'queries': {}, 'bundles': {}}

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

        default_contexts = client.default_contexts
        for table, prop in self.config['tables'].items():
            prop.setdefault('contexts', default_contexts)

        self.namespaces = []
        self.filters = []

        self.build_aliases()

    def merge_config(self, configpath):
        """
        Snarf in one more yaml file and return the dict, skip
        with a warning if it can't be parsed
        """
        logger.debug(f"Reading {configpath}")
        with open(configpath, "r", encoding="utf-8") as stream:
            try:
                new = yaml.safe_load(stream)
                if 'tables' not in new and 'queries' not in new and 'bundles' not in new:
                    logger.warning(f"{configpath} contains neither tables nor queries nor bundles")

            except yaml.YAMLError as exception:
                logger.warning(exception)
                new = {}

        filename = os.path.basename(configpath)

        for kind in ['bundles', 'queries', 'tables']:
            for name, prop in new.get(kind, {}).items():
                prop.setdefault('file', filename)

            self.config[kind] = {**self.config[kind], **new.get(kind, {})}

    def init_bundle(self, bundle):
        """
        Load the config for a bundle with tables and queries
        """

        logger.debug(f"  Loading config for bundle '{bundle}'")
        prop = self.bundles.get(bundle, {})
        for query in prop.get('queries', {}):
            self.show.append(query)
            self.init_query(query)
        for table in prop.get('tables', {}):
            self.show.append(table)
            self.init_table(table)

    def init_query(self, query):
        """
        Load the config for a query with its tables
        """

        logger.debug(f"  Loading config for query '{query}'")
        prop = self.queries.get(query, {})

        # append pre-defined parameters to the global list
        if 'namespaces' in prop:
            self.namespaces.extend(prop['namespaces'])
        if 'filters' in prop:
            self.filters.extend(prop['filters'])
        if 'patterns' in prop:
            self.filters.extend(prop['filters'])

        for table in prop.get('tables', {}):
            self.init_table(table)

    def init_table(self, table):
        """
        Load the config for a table
        """

        parsed = self.tables.get(table, {}).get('parsed', False)
        if parsed:
            return

        logger.debug(f"  Loading config for table '{table}'")
        prop = self.tables.get(table, {})

        if not prop:
            logger.error(f"Can't find table '{table}'")
            sys.exit(1)

        prop['parsed'] = True

        # append pre-defined parameters to the global list
        if 'namespaces' in prop:
            self.namespaces.extend(prop['namespaces'])
        if 'filters' in prop:
            self.filters.extend(prop['filters'])
        if 'patterns' in prop:
            self.filters.extend(prop['filters'])

        # for fields we need to compile the path
        for field, path in prop.get("fields", {}).items():
            if isinstance(path, dict):
                for subfield, subpath in path.items():
                    prop["fields"][field][subfield] = parse(subpath)

            elif isinstance(path, list):
                prop["fields"][field] = [parse(path[0])] + ['unroll' if f == 'unroll' else eval(f) for f in path[1:]]

            elif isinstance(path, str):
                prop["fields"][field] = parse(path)

    def build_aliases(self):
        """
        Amend the config data with generated aliases and a reverse map
        """

        # aliases point at a list of aliases for named bundles, queries, or tables
        self.aliases = dict()

        # unaliases are a reverse mapping of the above
        self.unaliases = dict()

        # a simple method to go for initial characters of a name
        def shorten(name):
            if '-' in name:
                return ''.join([shorten(s) for s in name.split('-')])
            return name[:2]

        # load the predefined aliases first
        for kind in ['bundles', 'queries', 'tables']:
            for name, prop in getattr(self, kind).items():
                for alias in prop.get('aliases', []):
                    self.aliases.setdefault(name, []).append(alias)
                    self.unaliases[alias] = name

        # for the rest of the entities, give aliases as first come, first served
        for kind in ['bundles', 'queries', 'tables']:
            for name, prop in getattr(self, kind).items():
                if not prop.get('aliases', []):
                    alias = shorten(name)
                    if alias not in self.unaliases:
                        self.aliases.setdefault(name, []).append(alias)
                        self.unaliases[alias] = name
                        prop['aliases'] = [alias]

    def init_config(self, args=[], patterns=[]):
        """
        Use a bit of heuristic to guess what the user asked for; args
        are taken to be bundles, queries, or tables, and patterns
        are taken at face value. If an arg is not found but there are
        other args already in the queue, then take an arg as another pattern
        """

        self.show = []
        self.patterns = patterns

        for arg in args:
            arg = self.unaliases.get(arg, arg)
            if arg in self.bundles.keys():
                self.init_bundle(arg)
            elif arg in self.queries.keys():
                self.show.append(arg)
                self.init_query(arg)
            elif arg in self.tables.keys():
                self.show.append(arg)
                self.init_table(arg)
            else:
                self.patterns.insert(0, arg)

            logger.debug(f"  Init config loop: arg {arg} in args {args} patterns {self.patterns}")

        if not self.show:
            logger.debug("Nothing to show, so loading 'list' instead")
            self.init_bundle('list')

    @property
    def tables(self):
        """All available tables"""
        return self.config["tables"] or {}

    @property
    def queries(self):
        """All available queries"""
        return self.config["queries"] or {}

    @property
    def bundles(self):
        """All available bundles"""
        return self.config["bundles"] or {}

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
