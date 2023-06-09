# python-kubectl-query

Query multiple cluster resources and join them together as tables

[![Build Status](https://github.com/gunther788/python-kubectl-query/workflows/build/badge.svg)](https://github.com/gunther788/python-kubectl-query/actions)
[![Coverage Status](https://coveralls.io/repos/github/gunther788/python-kubectl-query/badge.svg?branch=main)](https://coveralls.io/github/gunther788/python-kubectl-query?branch=main)
[![PyPi](https://img.shields.io/pypi/v/python-kubectl-query)](https://pypi.org/project/python-kubectl-query)
[![Licence](https://img.shields.io/github/license/gunther788/python-kubectl-query)](LICENSE)

## A Tour

Say you've got pods using persistent storage provided by NetApp Trident, and you'd like to know:

* which trident volumes are not in use anymore
* which trident volumes are used on which node
* as you're mucking about with StorageClasses and the topologies, you'd like to make sure
  that the pods are scheduled on the same nodes as Trident will provide the storage

These kinds of questions require:

* manually going through output of `kubectl`, possibly glued together with some scripting
* custom scripts that gather exactly the targeted combination of data, resulting in a series of custom scripts
* a fancy GUI that happens to show exactly what you're looking for

### Tables

Instead, let's define building blocks (`tables`) of data that are extracted from individual Kuberentes resources.

Example:

```yaml
tables:

  pods-pvcs:
    note: Pods with PVCs
    api_version: v1
    kind: Pod
    fields:
      pod: "$.metadata.name"
      namespace: "$.metadata.namespace"
      node: "$.spec.nodeName"
      pvc: "$.spec.volumes[*].persistentVolumeClaim.claimName"

  pvcs:
    note: PersistentVolumeClaims with Volumes
    api_version: v1
    kind: PersistentVolumeClaim
    fields:
      pvc: "$.metadata.name"
      namespace: "$.metadata.namespace"
      volume: "$.spec.volumeName"
      pvcphase: "$.status.phase"

  pvs:
    note: PersistentVolumes with StorageClass
    api_version: v1
    kind: PersistentVolume
    fields:
      volume: "$.metadata.name"
      pvc: "$.spec.claimRef.name"
      namespace: "$.spec.claimRef.namespace"
      storageclass: "$.spec.storageClassName"
      pvphase: "$.status.phase"

  tridentvolumes:
    note: TridentVolumes with size and health
    api_version: trident.netapp.io/v1
    kind: TridentVolume
    fields:
      volume: "$.metadata.name"
      state: "$.state"
      orphaned: "$.orphaned"
```

Note that the fields are intentionally renamed to match one another; a `pvc` in `pods-pvcs` and a `pvc` in `pvcs` are
the same pieces of data, used to join the tables together.

`kubectl query tridentvolumes` (or any other table) will show you exactly those fields defined above. The same
resource can be defined multiple times, depending on the sets of fields and use cases of the table.

### Queries

Queries (`queries`) are then simply left-joined sets of tables defined above.

Example:

```yaml
queries:

  trident-pods:
    note: Trident Volumes with PVCs back to Pods
    tables:
      - tridentvolumes
      - pvs
      - pvcs
      - pods-pvcs

  pods-trident:
    note: Pods with PVCs to Trident Volumes
    tables:
      - pods-pvcs
      - pvcs
      - pvs
      - tridentvolumes
```

That's it -- we now have two queries that show a list of volumes and where (or not) they're used, and a list of
pods linked all the way through the PV/PVCs down to the volumes used.

Because of the way the tables are merged (left-join), the order matters: here we either start with all known
TridentVolumes and amend the data with everything up to Pods, or we start with Pods and amend the storage
data to that list -- the latter being smaller by all volumes allocated but unused.

## Install

```bash
# Install tool
pip3 install kubectl_query

# Install locally
make install
```

## Usage

```bash
/usr/local/bin/kubectl-query ...
```

or as `krew` plugin

```bash
kubectl query ...
```

## Development

```bash
# Get a comprehensive list of development tools
make help
```

## Standing on the Shoulders of Giants

### Python client library for Kubernetes

[https://github.com/kubernetes-client/python](https://github.com/kubernetes-client/python) to connect to
the cluster in the current context.

### Click

[https://click.palletsprojects.com/](https://click.palletsprojects.com/) is used to handle all the arguments and options.

### ANSI Colors

[https://github.com/jonathaneunice/colors/](https://github.com/jonathaneunice/colors/) to colorize the output, inspired
by [https://github.com/hidetatz/kubecolor](https://github.com/hidetatz/kubecolor).

### JSONPath Next-Generation

[https://github.com/h2non/jsonpath-ng](https://github.com/h2non/jsonpath-ng) is used to parse the json data provided
by the Kubernetes API and select the fields of interest.

### Pandas & Numpy

[https://github.com/pandas-dev/pandas](https://github.com/pandas-dev/pandas) and [https://numpy.org/](https://numpy.org/)
provide an insane amount of functionality, but for this project it does things really well:

* hold tabular data in DataFrames
* join DataFrames of different sources together by simply matching common columns
* provide filtering

### Tabulate

[https://github.com/astanin/python-tabulate](https://github.com/astanin/python-tabulate) handles the output processing
almost entirely; there's a pseudo table format here called `color` that is `plain` with colored output, but any
format supported by `tabulate` can be selected.
