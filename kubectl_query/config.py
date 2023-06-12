import glob
import importlib.resources
import ipaddress  # noqa: F401
import logging
import os

import pandas as pd
import yaml
from jsonpath_ng.ext import parse
from kubernetes import config as kubeconfig
from kubernetes import dynamic

logger = logging.getLogger('kubectl-query')


class Config:
    """
    Represents the config file and does sanity checking of the input
    """

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

    def __init__(self, configpaths, set_context):
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

        # let's have a look at the contexts available
        known_contexts, default_context = kubeconfig.list_kube_config_contexts()
        known_contexts = [context['name'] for context in known_contexts]
        default_context = set_context or default_context['name']
        logger.debug(f"Loaded contexts: {known_contexts}, default '{default_context}'")
        self._client = {}

        # process tables
        logger.debug("Compiling configs:")
        for table, prop in self.config.get("tables", {}).items():
            context = prop.get('context', default_context)
            logger.debug(f"  Loading config for table '{table}' with context '{context}'")

            # skip if we set the context and it's not known
            if context not in known_contexts:
                logger.warning(f"Table '{table}' refers to unknown context '{context}', skipping...")
                continue

            # load Kubernetes client once for each context used
            prop.setdefault('context', context)
            if context not in self._client:
                try:
                    self._client[context] = dynamic.DynamicClient(kubeconfig.new_client_from_config(context=context))
                except Exception as exc:
                    logger.warning(f"Can't load Kubernetes config: {exc}")
                    pass

            # for fields we need to compile the path
            for field, path in prop.get("fields", {}).items():
                if isinstance(path, dict):
                    for subfield, subpath in path.items():
                        prop["fields"][field][subfield] = parse(subpath)

                elif isinstance(path, list):
                    prop["fields"][field] = [parse(path[0])] + [eval(f) for f in path[1:]]

                elif isinstance(path, str):
                    prop["fields"][field] = parse(path)

        # process and queries
        for query, prop in self.config.get("queries", {}).items():
            logger.debug(f"  Loading config for query {query}")
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

        logger.debug(f"Unlias map: {unalias}")
        return unalias

    def check_queries(self, iq):
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
            return oq

        errors = list(filter(lambda query: query not in available, oq))
        logger.error(f"{errors} are neither tables nor queries nor aliases for them")
        return []

    def client(self, context):
        """Just the API client"""
        return self._client[context]

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
                    'context': prop.get('context', '-'),
                    'references': ', '.join(prop.get('tables', [])) or None,
                    'note': prop.get('note', ""),
                }
            )

        return pd.DataFrame(available)
