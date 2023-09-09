from multiprocessing import Pool
import subprocess


def run_comand(path):
	print(f"checking {path}")
	command = f"kubectl exec {path} -n dev-oddsbender -- pgrep -a python "
	subprocess.Popen(command, shell=True)

pool = Pool()
proc = subprocess.Popen(["kubectl get pods -o json | jq -r '.items[].metadata.name' | grep prop"], shell=True, stdout=subprocess.PIPE)
deployments = proc.stdout.read().decode("utf-8")
print(type(deployments))
print(str(deployments).split('\n'))
pool.map(run_comand, deployments)