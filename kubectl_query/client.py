import logging

from kubernetes import config as kubeconfig
from kubernetes import dynamic

logger = logging.getLogger('kubectl-query')


class Client:
    """
    Connections to the Kubernetes clusters
    """

    def __init__(self, contexts):
        """
        Set up a dynamic client to each of the contexts
        """

        logger.debug(f"Contexts: requested {contexts}")

        known_contexts, default_context = kubeconfig.list_kube_config_contexts()
        self._known_contexts = [context['name'] for context in known_contexts]

        if contexts:
            if 'all' in contexts:
                self._default_contexts = self._known_contexts
            else:
                self._default_contexts = contexts

        else:
            self._default_contexts = [default_context['name']]

        self._client = {}

        for context in self.default_contexts:
            self.client(context)

    @property
    def known_contexts(self):
        return self._known_contexts or []

    @property
    def default_contexts(self):
        return self._default_contexts or []

    def client(self, context):
        if context not in self._client:
            logger.debug(f"  Loading context '{context}'")
            try:
                self._client[context] = dynamic.DynamicClient(kubeconfig.new_client_from_config(context=context))
            except Exception as exc:
                logger.warning(f"Can't load Kubernetes config: {exc}")
                pass

        return self._client[context]
