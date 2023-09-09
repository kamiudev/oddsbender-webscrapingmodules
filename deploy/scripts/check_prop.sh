declare -a scraper_deployments

scraper_deployments=$(kubectl get pods -o json | jq -r '.items[].metadata.name' | grep prop)

for deployment in ${scraper_deployments[@]}
do
	echo $deployment
	kubectl exec $deployment -n prod-oddsbender -- pgrep -a python 
done