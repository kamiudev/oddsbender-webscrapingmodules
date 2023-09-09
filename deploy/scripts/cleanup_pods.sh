#!/bin/bash
# Get the list of Pods, then select the items that have
# been evicted, sort by the startTime (ascending), then 
# select all but the most recent 3.  Then pass just the 
# names of those Pods to kubectl to be deleted
kubectl delete pod $(kubectl get pods | awk '/Evicted/ {print $1}')