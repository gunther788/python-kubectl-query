import glob
import ipaddress  # noqa: F401
import logging
import os

import yaml
from colors import color
from jsonpath_ng import parse
from kubernetes import config as kubeconfig
from kubernetes import dynamic
from kubernetes.client import api_client

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

        self.config['tables'] = {**self.config['tables'], **new.get('tables', {})}
        self.config['queries'] = {**self.config['queries'], **new.get('queries', {})}

    def __init__(self, configpaths):
        """
        Parse the configuration files or directories and compile the
        JSON paths needed to select fields later on
        """

        try:
            self._client = dynamic.DynamicClient(api_client.ApiClient(configuration=kubeconfig.load_kube_config()))
        except Exception as exc:
            logger.warning(f"Can't load Kubernetes config: {exc}")
            pass

        self.config = {'tables': {}, 'queries': {}}

        for configpath in configpaths:
            if os.path.isfile(configpath):
                self.merge_config(configpath)
            elif os.path.isdir(configpath):
                for configfile in glob.glob(f"{configpath}/*.yaml"):
                    self.merge_config(configfile)
            else:
                logger.warning(f"Don't know what to do with '{configpath}'")

        logger.debug("Compiling configs:")

        # process tables
        for table, prop in self.config.get("tables", {}).items():
            logger.debug(f"  Loading config for table {table}")
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
            for table in prop['tables']:
                if table not in self.config['tables']:
                    logger.warning(f"Query '{query}' makes use of an unknown table '{table}'")

    def get_available_queries(self):
        """
        Put together a message with all the config data
        """

        messages = [
            "",
            "Query multiple cluster resources and join them together as tables",
        ]

        messages.extend(["", "Tables:", ""])
        for table, prop in self.config.get("tables", {}).items():
            messages.append(f"  {color(table, fg='yellow')}")
            if prop.get("note"):
                messages.append(f"    {prop['note']}")

        messages.extend(["", "Queries:", ""])
        for query, prop in self.config.get("queries", {}).items():
            messages.append(f"  {color(query, fg='yellow')}")
            if prop.get("note"):
                messages.append(f"    {prop['note']}")
        messages.append("")

        return messages

    def check_queries(self, queries):
        """
        Make sure that all requested queries are defined, otherwise show
        the user what we have
        """

        available = list(self.config.get("queries", {}).keys()) + list(self.config.get("tables", {}).keys())

        if all(query in available for query in queries):
            return queries

        errors = list(filter(lambda query: query not in available, queries))
        logger.error(f"{errors} are neither tables nor queries")
        return []

    @property
    def client(self):
        """Just the API client"""
        return self._client

    @property
    def tables(self):
        """All available tables"""
        return self.config["tables"]

    @property
    def queries(self):
        """All available queries"""
        return self.config["queries"]
