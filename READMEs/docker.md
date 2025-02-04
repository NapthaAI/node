# Setting up your Naptha Node with Docker

The Naptha Node providers Dockerfiles and a `docker-compose.yml` file. The node depends on a number of services, and this modular approach will allow you to run a single command (`docker compose up`) to get everything up and running, or to only start the services that you need, for example if you have to use external rabbitmq/postgres/surrealdb services.

## Configuring your Naptha Node

Start by copying the provided `.env` file:

```shell
cp .env.example .env
```

- `LAUNCH_DOCKER`: Set to True if you want to launch the node using Docker.
- `LLM_BACKEND`: Should be set to "ollama" if not using a GPU, or to VLLM if you want to use a GPU.
- `NUM_GPUS`: The vLLM docker compose configuration is intended to run on either a single GPU or an 8x A100 80GB node -- running it on a device with fewer GPUs or with less vRAM per GPU will require modifying the number of models that are running and/or model context length, etc.
- `OLLAMA_MODELS`: If using ollama, set this to the models you want to use, separated by commas. By default, the node will use the Nous Research Hermes 3 model. By default, ollama models will be downloaded to `node/inference/ollama` and mounted as a bind volume in the ollama container.
- `VLLM_MODELS`: If using VLLM, you currently need to set this in the `docker-compose.vllm.yml` and `docker-compose.single-gpu.yml` files and the corresponding `litellm_config.vllm.yml` [LiteLLM configuration file](https://docs.litellm.ai/docs/proxy/configs).
- `HUGGINGFACE_TOKEN`: If you plan to access private/gated models (such as Llama 3.1 8B, or others by Meta and Mistral) you need to make sure to set a HuggingFace acccess token in the `.env` file. The default vLLM compose file `docker-compose.vllm.yml` accesses llama 3.1, so make sure to request access to this model.
- `HF_HOME`: If you plan to serve models with vLLM, make sure to set the `HF_HOME` environment variable to the path to your HuggingFace cache directory, so the models can be mounted as volumes rather than being re-downloaded every time a container is created. Your cache directory will be mounted into vLLM containers, so that models are downloaded and cached on your disk and can be easily re-loaded and re-used. If you're not sure what to set this to, `/home/<your user>/.cache/huggingface` is the default path on linux and MacOS systems.

For advanced configuration settings, see the [Advanced Configuration](READMEs/advanced.md) guide.


## Launching the Naptha Node

You can run the node using:

```bash
bash launch.sh
```

This will automatically call `docker compose up` with the appropriate compose file based on your configuration. 

The images will be pulled from `napthaai/node:latest` on Docker hub. It will not build the image from source (see the development workflows in the [Advanced Configuration](READMEs/advanced.md) guide to build the container from source.)

You can also run the node using `docker compose up` directly, with the appropriate compose file (there is more manual effort required: you will need to be careful that the litellm config and config variables are set correctly):

1. Without inference: `docker-compose -f docker-compose.yml up`
2. With ollama: `docker-compose -f docker-compose.ollama.yml up`
3. Run several <10B models and an embedding model with vLLM: `docker-compose -f docker-compose.vllm.yml up`
4. Run a single GPU with vLLM: `docker-compose -f docker-compose.single-gpu.yml up`
5. Run in development mode: `docker-compose -f docker-compose.development.yml up`



### Development Mode 

The development docker-compose file `docker-compose.development.yml` file has several notable differences from the production-ready docker compose files:

1. the `node-app` has bind mounts configured to the location of the node's and worker's source code. Additionally, it has "watch mode" enabled when run with `docker compose -f docker-compose.development.yml watch` enabled. Changes to the application's source code (on your filesystem!) will be mirrored in the container, and saving those changes will cause the process in the container to be restarted and updated with the changes, allowing for rapid iteration - changes to dependencies or environment variables (e.g. `.env`) still require rebuilding the container.
2. There is an additional `surrealdb` service in the compose file if you wish to use the local hub by setting `LOCAL_HUB=True` in `config.py`
3. _The container for the node server and celery worker will be built from source, rather than being pulled from dockerhub_.

### Partial Compose configuration (for development)

Running a configuration where some services (e.g. RMQ, postgres) are run in containers and other applications, e.g. the node and worker is possible, though documentation and support is less robust. Generally, here is the approach you should take:

1. Install this repository's dependencies with `poetry`
2. Alter your `/etc/hosts` file to add the list of service names from docker compose to your hosts file as `127.0.0.1`. 

    Note that it is not necessary to add inference services (`ollama`, `vllm-*`) to this list since they are only accessed directly by `litellm`, unless you are running the inference services _or_ liteLLM outside of docker compose:

    ```shell
    sudo echo "127.0.0.1 node-app pgvector rabbitmq litellm" >> /etc/hosts
    ```

    or, if you want to run vllm or ollama or litellm outside of docker compose, you need to run:

    ```shell 
    sudo echo "127.0.0.1 node-app pgvector rabbitmq litellm" >> /etc/hosts
    sudo echo "127.0.0.1 ollama vllm-0 vllm-1 vllm-2 vllm-3 vllm-4 vllm-5 vllm-6 vllm-7" >> /etc/hosts
    ```

    to ensure that they are added to your hosts file as well.

3. Ensure that any services which you are _not_ running in docker are not listed as dependencies in other services via the `depends_on` key. if a service you are running outside of docker _is_ listed as a dependency for another service, you must remove the service from the dependency list.

4. Start the services you want in docker with docker, with compose:
   For example, to run the node with ollama, and to serve everything except the node app + celery worker in docker, 
    you would run this:
   ```shell 
   docker compose -f docker-compose.ollama.yml up rabbitmq pgvector ollama litellm  
   ```
   and then you would start the node app and celery worker separately. 

    Alternatively for example, to run the node plus vLLM for inference, with everything except the node app + celery worker in docker, 
   you would run:
   ```shell 
   docker compose -f docker-compose.vllm.yml up rabbitmq pgvector litellm vllm-0 vllm-1 vllm-2 vllm-3 vllm-4 vllm-5 vllm-6 vllm-7
   ```
   and then you would start the app + celery worker independently.

When using `docker compose -f <...> watch`, changes to python dependencies, binary dependencies, or environment variables in `.env` will still require that the container be re-built. changes to `config.py` will be reflected automatically.






