import logging
import pkgutil
import sys

import yaml
from colors import color
from jsonpath_ng import parse
from kubernetes import config as kubeconfig
from kubernetes import dynamic
from kubernetes.client import api_client

logger = logging.getLogger(__name__)


class Config:
    """
    Represents the config file and does sanity checking of the input
    """

    def __init__(self, configfile):
        """
        Parse the configuration file and compile the JSON paths needed
        to select fields later on
        """

        try:
            self._client = dynamic.DynamicClient(api_client.ApiClient(configuration=kubeconfig.load_kube_config()))
        except Exception as exc:
            logger.warning(f"Can't load Kubernetes config: {exc}")
            pass

        if configfile:
            self.configfile = configfile
            logger.debug(f"Reading {configfile}")
            with open(configfile, "r", encoding="utf-8") as stream:
                try:
                    self.config = yaml.safe_load(stream)

                except yaml.YAMLError as exception:
                    logger.critical(exception)
                    sys.exit(2)

        else:
            stream = pkgutil.get_data(__name__, "config.yaml")
            self.config = yaml.safe_load(stream)

        # process tables
        for table, prop in self.config.get("tables", {}).items():
            logger.debug(f"  Loading config for table {table}")
            # for fields we need to compile the path for l
            for field, path in prop.get("fields", {}).items():
                prop["fields"][field] = parse(path)

        # process and queries
        for query, prop in self.config.get("queries", {}).items():
            logger.debug(f"  Loading config for query {query}")

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
