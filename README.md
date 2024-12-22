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

## Launch with docker

Copy the example env file and add a PRIVATE_KEY:

```bash
cp .env.example .env
```

Then run the node in docker:

```bash
bash launch_docker.sh
```

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

## To cleanup

```
make remove
```

## Cross-Platform Dockerfile
The Naptha node uses a cross-platform Dockerfile intended for use with `docker buildx`. This is automatically used by 
Naptha's CI/CD, so when you pull the image, the right architecture will be used. To build the image 
with `docker buildx` yourself, you must first install Docker on your system. Once you have done that, complete the following
steps to enable the `buildx` plugin:


```shell 
docker buildx install # install the buildx plugin
docker buildx create --name builder --use # create a builder 
docker build use builder
```

Once you have done this, you can build the `buildx.Dockerfile` for your platform of choice.

Note that if you are specifying a _single_ target platform with `--platform`, you can use `--load` to load the image
into your local docker cache. If you are building for multiple platforms with `--platform`, you must use `--push` to 
push the manifests up to your dockerhub / other container repo, since the local docker cache
does not support manifest lists for multi-platform builds. In that case, you need to specify a full container tag of 
`account/repository:tag`

```shell
# for ARM CPUs only:
docker buildx build \
  --platform linux/arm64 \
  -t example-docker-tag \
  -f buildx.Dockerfile \
  --load . 
  
# for multiple target platforms:
docker buildx build \
  --platform linux/arm64,linux/amd64 \
  -t account/repository:tag \
  -f buildx.Dockerfile \ 
  --push .


# for GPU-accelerated inference with ollama or vLLM; use an nvidia/cuda base image. replace 12.4.1 with your CUDA version;
# see https://hub.docker.com/r/nvidia/cuda/tags for a list of supported images.
docker buildx build \
    --platform linux/arm64 \
    --build-arg BASE_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04 \ 
    -t yourdockerprofile/yourrepo:yourtag \
    -f buildx.Dockerfile \
    --load .
```