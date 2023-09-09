## Specifies that Tilt is allowed to run against the specified k8s context names.
## In this case we want to run the app against the XENA Training Cluster
## https://docs.tilt.dev/api.html#api.allow_k8s_contexts
allow_k8s_contexts('oddsbender')

## Run `helm template` on a given directory that contains a chart and return the fully rendered YAML.
## The `name` and `namespace` should be updated with the assigned student number.
## https://docs.tilt.dev/api.html#api.helm
yaml = helm(
  'deploy',
  # The release name, equivalent to helm --name
  name='dev-oddsbender',
  # REPLACE HERE - The namespace to install in, equivalent to helm --namespace
  namespace='dev-oddsbender',
  # The values file to substitute into the chart.
  values=[
    './conf-deploy/common.values.yaml',
    './conf-deploy/development.scrapers.yaml',
    './conf-deploy/development.values.yaml'
  ]
)

## Apply the helm chart object created in above step.
## https://docs.tilt.dev/api.html#api.k8s_yaml
k8s_yaml(yaml)

## Build the front-end container with the development version of the Dockerfile
## Do not trigger a build when the backend, Tiltfile, or .vscode files/folders are updated
## Execute a live update of the code whenever a file in the frontend folder is changed.
## When the package.json or package-lock.json are changed trigger an npm install inside of the pod.
## https://docs.tilt.dev/api.html#api.docker_build
#barstool
docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/basketball', '.',
    dockerfile='build/basketball/Dockerfile',
    ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
    live_update=[
        sync('./basketball', '/app'),
    ]
)
docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/football', '.',
    dockerfile='build/football/Dockerfile',
    ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*']
)

# #bet365
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/bet365-basketball', '.',
#     dockerfile='build/bet365-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/bet365-football', '.',
#     dockerfile='build/bet365-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )

# #betmgm
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/betmgm-basketball', '.',
#     dockerfile='build/betmgm-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/betmgm-football', '.',
#     dockerfile='build/betmgm-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )

# #caesars
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/caesars-basketball', '.',
#     dockerfile='build/caesars-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/caesars-football', '.',
#     dockerfile='build/caesars-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )

# #Draftkings
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/draftkings-basketball', '.',
#     dockerfile='build/draftkings-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/draftkings-football', '.',
#     dockerfile='build/draftkings-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )

# #fanduel
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/fanduel-basketball', '.',
#     dockerfile='build/fanduel-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/fanduel-football', '.',
#     dockerfile='build/fanduel-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )

# #sugarhouse
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/sugarhouse-basketball', '.',
#     dockerfile='build/sugarhouse-basketball/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./basketball', '/app'),
#     ]
# )
# docker_build('157485876214.dkr.ecr.us-east-2.amazonaws.com/sugarhouse-football', '.',
#     dockerfile='build/sugarhouse-football/Dockerfile',
#     ignore=['csv', 'Tiltfile', '.vscode', 'deploy/*', '.venv/*'],
#     live_update=[
#         sync('./', '/app'),
#     ]
# )
## Configure port forwarding to connect localhost directly to the port the app is running on in the pod.
## Port 3000 - Frontend Pod
## Port 5000 - Backend Pod
## Port 9229 - NodeJS Debugging
## https://docs.tilt.dev/api.html#api.k8s_resource
# k8s_resource('attendance-tracker', port_forwards=['3000:3000', '5000:5000', '9229:9229'])
