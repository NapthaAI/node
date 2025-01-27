                 █▀█                  
              ▄▄▄▀█▀            
              █▄█ █    █▀█        
           █▀█ █  █ ▄▄▄▀█▀      
        ▄▄▄▀█▀ █  █ █▄█ █ ▄▄▄       
        █▄█ █  █  █  █  █ █▄█        ███╗   ██╗ █████╗ ██████╗ ████████╗██╗  ██╗ █████╗ 
     ▄▄▄ █  █  █  █  █  █  █ ▄▄▄     ████╗  ██║██╔══██╗██╔══██╗╚══██╔══╝██║  ██║██╔══██╗
     █▄█ █  █  █  █▄█▀  █  █ █▄█     ██╔██╗ ██║███████║██████╔╝   ██║   ███████║███████║
      █  █   ▀█▀  █▀▀  ▄█  █  █      ██║╚██╗██║██╔══██║██╔═══╝    ██║   ██╔══██║██╔══██║
      █  ▀█▄  ▀█▄ █ ▄█▀▀ ▄█▀  █      ██║ ╚████║██║  ██║██║        ██║   ██║  ██║██║  ██║
       ▀█▄ ▀▀█  █ █ █ ▄██▀ ▄█▀       ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝        ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
         ▀█▄ █  █ █ █ █  ▄█▀                             Orchestrating the Web of Agents
            ▀█  █ █ █ █ ▌▀                                                 www.naptha.ai
              ▀▀█ █ ██▀▀                                                    
 

# NapthaAI Node  

Naptha is a framework and infrastructure for developing and running multi-agent systems across many devices. The Naptha Node packages everything that your need to run agents locally, that interact with other agents in the network. 

- [Local Inference](node/vllm/): Using either VLLM (or Ollama). Not many open source models support tool calling out of the box. The Naptha Node (soon) supports tool calling with 8 open source models, with more to come.
- [LiteLLM Proxy Server](node/litellm): A proxy server that provides a unified OpenAI-compatible API interface for multiple LLM providers and models. This allows seamless switching between different models while maintaining consistent API calls.
- [Local Server](node/server): The Naptha Node runs a local server that can be accessed by other agents in the network (via HTTP, Web Sockets, or gRPC). Agents and other modules that you publish on Naptha are accessible via API.
- [Local Storage](node/storage/db): Naptha Nodes support the deployment of Environment modules, which are things like group chats (think WhatsApp for agents), information boards (Reddit for agents), job boards (LinkedIn for agents), social networks (Twitter for agents), and auctions (eBay for agents). The state of these modules is stored in a local database (postgres) and file system. The Naptha Node also stores details of module runs and (soon) model inference (token usage, costs etc.) in the local database.
- [Module Manager](node/module_manager.py): Supports downloading and installation of modules (agents, tools, agent orchestrators, environments, and personas) from GitHub, HuggingFace and IPFS. 
- [Message Broker and Workers](node/worker/): The Naptha Node uses asynchronous processing and message queues (RabbitMQ) to pass messages between modules. Modules are executed using either Poetry or Docker. 

- (Optional) [Local Hub](node/storage/hub): The Naptha Node can run a local Hub, which is a registry for modules (agents, tools, agent orchestrators, environments, and personas) and nodes by setting LOCAL_HUB=True in the Config. This is useful for testing locally before publishing to the main Naptha Hub. For the Hub DB, we use SurrealDB.

You can change the settings for running the Naptha node via the [Config](node/config.py).

# Prerequisites

If using MacOS, you will need to install brew first.

# Install and run

From source:

```bash
git clone https://github.com/NapthaAI/node.git
cd node
```

## Launch with systemd

Then run the node:

```bash
bash launch.sh
```

The first time you launch, you will be prompted about whether (i) to generate a private key, and (ii) to input a Stability API key, which is needed if you would like to run the image agent examples. If you choose not to, you can always edit the .env file manually later.

After a few minutes you should see ```[System] Setup complete. Applications are running.```


Before running agents and multi-agent orchestrators via the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk), you should wait to check that the servers set up correctly by running the following in a new terminal window. On Linux:

```bash
journalctl -u nodeapp_http -n 100 -f
```

On MacOS:

```bash
tail -n 100 -f /tmp/nodeapp_http.err
```

You should see ```Uvicorn running on http://0.0.0.0:7001```. 


# Run AI agents on your node

To run agents, keep your node running and follow the instructions using the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk). In the SDK repo, you should set the NODE_URL to the URL of your local node (default is http://localhost:7001).

# Troubleshooting

If you get an unexpected error when running agents and multi-agent orchestrators, you can check the logs for the servers using:

```bash
journalctl -u nodeapp_http -n 100 -f
```

On MacOS:

```bash
tail -n 100 -f /tmp/nodeapp_http.out
```

You can also check the logs of the workers, which may show an error if you e.g. have a bug in the code you wrote for an agent package. On Linux:

```bash
journalctl -u celeryworker -n 100 -f
```

On MacOS:

```bash
tail -n 100 -f /tmp/celeryworker.err
```

## Stop

If using systemd:

```
bash stop_service.sh
```

If using docker:

```
bash stop_docker.sh
```

## To restart the node

As an alternative to stopping and re-launching the node, you can use the `make restart-node` command to perform a complete restart of various node components:

1. Cleans up by removing (you can do this individually using `make remove`):
   - All `__pycache__` directories
   - `.venv` virtual environment directory 
   - `node/storage/hub/modules` directory

2. Cleans the pyproject.toml file

3. Rebuilds dependencies:
   - Runs `poetry lock`
   - Runs `poetry install` 

4. Restarts all services in parallel:
   - Restarts all node servers (HTTP and secondary servers)
   - Restarts the Celery worker

This is useful when you want to do a complete reset and restart of the node, especially after making code changes or if you're experiencing issues.

## To reset the databases

If you are having issues related to the databases on launch (e.g. from alembic with postgres), you may want to reset them. Be warned, this will delete all data in the databases. For the hub DB, you can reset it by running:

```
make remove-hub
```

For the local DB, you can do a soft reset it by running (this one should be run before running `bash stop_service.sh`):

```
make local-db-reset
```
If after the soft reset, you are still having issues related to the database on launch, you can run a hard reset using:

```
make local-db-hard-reset
```

# Running the node with Docker & Docker Compose
The Naptha Node providers Dockerfiles and a `docker-compose.yml` file that facilitate getting the node 
up-and-running as quickly and easily as possible. The node depends on a number of services, and this moduler approach 
will allow you to run a single command (`docker compose up`) to get everything up and running, or to 
only start the services that you need, for example if you have to use external rabbitmq/postgres/surrealdb services.

## Configuring Your Environment

### Customizing your `config.py` file



### Customizing your `.env` file
Start by copying the provided `.env` file:
```shell
cp .env.example .env
```
- note that the `RMQ_*` variables will be passed in to create the default RMQ user, and to authenticate with RMQ. `RMQ_HOST` 
should be set to `rabbitmq` in this case, since that's the name of the rabbitmq service in the docker-compose files. The
username and password can be whatever you want.
- the `HUB_DB_SURREAL_*` variables will be used for the local hub via surrealDB, if using the development compose file.
- the `LITELLM_*` variables are required for LiteLLM, which is the proxy used for 
aggregating LLM APIs from e.v. vLLM, ollama, OpenAI, etc.
You should pick secure values for these.
- if you plan to use the default vLLM compose file, you need to make sure to set `HUGGINGFACE_TOKEN` to a hugging face acccess token
that has access to Llama 3.1 8B. Similarly, if you plan to access other private/gated models (e.g. those by Meta and Mistral),
make sure to set your hugging face access token in `.env`
- if you plan to serve models with vLLM, make sure to set the `HF_HOME` environment variable to the path to your hugging face
cache directory, so the models can be mounted as volumes rather than being re-downloaded every time a container is created. 
This will mount your cache directory into vLLM containers, so that models are downloaded and cached on your disk and can be
easily re-loaded and ure-used. The default hugging face cache directory is `/home/<your user>/.cache/huggingface`, unless you have 
changed it. 


## Running the Node

### Production Mode (Without Inference)

If you are running LiteLLM externally to the node, you can specify the `LITELLM_URL` value in `node/config.py`, and add `LITELLM_MASTER_KEY` 
in your `.env` file so that your node is able to access your LiteLLM instance.
Then, run:

```shell 
docker-compose -f docker-compose.yml up
```

to launch the node's applications and services.

### Production Mode (With inference)
If you are _not_ running LiteLLM already, you can select to either run a model with `ollama` (good for local development on CPU), 
or with vLLM. In either case, you should set `LITELLM_URL` in `config.py` to `http://litellm:4000`, which is the 
host and port of the LiteLLM container in the inference-enabled compose configurations.

#### Ollama
A default [LiteLLM configuration file](https://docs.litellm.ai/docs/proxy/configs) has been provided at `litellm_config.ollama.yml`, which matches  
the ollama container's default model of `hermes3:8b` (served as `NousResearch/Hermes-3-Llama-3.1-8B`), but you can 
change the served model if you would like:
1. You can change the model(s) you want to run, by altering the entrypoint of the `ollama` service in `docker-compose.ollama.yml` to run 
a model other than `hermes3:8b`, 
2. Then, alter `litellm_config.ollama.yml` to reflect your selected model. The `model_name` in the LiteLLM configuration file should be the name to serve the model as, and the `model` should be `ollama_chat/<your model here>`, e.g. `ollama_chat/qwen2.5-coder`

Using either the default ollama container config & LiteLLM model _or_ your altered one, run:

```shell 
docker compose -f docker-compose.ollama.yml up
```
to start ollama, LiteLLM, and the node and its services.
_Please see the "Notes" section below for additional information about model serving & node usage 
with ollama_

#### vLLM
The vllm docker-compose file runs several < 10B models and an embedding model with vLLM.
(You can substitute TEI for vLLM for the embedding model, if you would like for broader model support).

A default [LiteLLM configuration file](https://docs.litellm.ai/docs/proxy/configs) has been provided that matches the 
served models in the vLLM docker compose file. 
You can alter the served model(s) by altering the `docker-compose.vllm.yml` file and its corresponding `litellm_config.vllm.yaml` 
LiteLLM configuration file. 

Using either the default configuration or your altered one, run:
```shell 
docker compose -f docker-compose.vllm.yml up
```
to start the LiteLLM proxy, the vLLM instances, and the node and its services. 


### Development Mode 
The development docker-compose file `docker-compose.development.yml` file has several notable differences 
from the production-ready docker compose files:
1. the `node-app` and `celery` services have bind mounts configured to the location of the node's and worker's source code.
Additionally, they have "watch mode" enabled when run with `docker compose -f docker-compose.development.yml watch` enabled. 
Changes to the application's source code (on your filesystem!) will be mirrored in the container, and saving those changes 
will cause the process in the container to be restarted and updated with the changes, allowing for rapid iteration
    - changes to dependencies or environment variables (e.g. `.env`) still require rebuilding the container.
2. There is an additional `surrealdb` service in the compose file if you wish to use the local hub by setting `LOCAL_HUB=True` in `config.py`
3. containers for the node server, celery worker, and storage API are build from source instead of being pulled from a container repository.

## Notes & "Gotchas"
- the vLLM docker compose container is intended to run on an 8x A100 80GB node -- running it on a device with fewer GPUs
or with less vRAM per GPU will require modifying the number of models that are running and/or model context length, etc.
- The `rabbitmq` and `postgres` containers have persistent volumes that will survive the containers being
shut down. Once the container has been started for the first time, the username and password values in the `.env` file 
cannot be changed without authentication failing, unless you run `docker compose -f <compose file name> down --volumes` 
to destroy the persistent volumes, and then rebuilding with `docker compose -f <compose file name> up`
   - `scripts/init.sql` is run the first time that the postgres container is launched, but its' results and the persisted 
postgres data are saved in postgres's named volume. If you want to re-run the script, you need to destroy the volume 
once the container is stopped 
- By default, ollama models will be downloaded to `node/ollama`, which is configured in the `.dockerignore` and mounted 
as a bind volume in the ollama container. This directory is also in the `.gitignore` so that models are not tracked in version control.
- Make sure to set the `HF_HOME` environment variable to the _path to your hugging face cache directory_ on your host;
this will be mounted into vLLM containers (if you are using vLLM) so that models don't have to be re-downloaded each 
time that the containers are restarted. If you're not sure what to set this to,  `/home/<your user>/.cache/huggingface` 
is the default path on linux and MacOS systems.
- The `HUGGINGFACE_TOKEN` can be set in the `.env` file and is passed into vLLM containers, so that (a) you can access 
private models if you want, and (b) you can access models that require agreeing to a license such as Llama 3.x models. 
The default vLLM compose file `docker-compose.vllm.yml` accesses llama 3.1, so make sure to request access to this model
and add your token to `.env` if you want to use it, otherwise remove it. 
- When using `docker compose -f <...> watch`, changes to python dependencies, binary dependencies, or environment variables 
in `.env` will still require that the container be re-built. changes to `config.py` will be reflected automatically.
