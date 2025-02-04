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

- [Local Inference](node/inference/): Using either VLLM (or Ollama). Not many open source models support tool calling out of the box. The Naptha Node (soon) supports tool calling with 8 open source models, with more to come.
- [LiteLLM Proxy Server](node/inference/litellm): A proxy server that provides a unified OpenAI-compatible API interface for multiple LLM providers and models. This allows seamless switching between different models while maintaining consistent API calls.
- [Local Server](node/server): The Naptha Node runs a local server that can be accessed by other agents in the network (via HTTP, Web Sockets, or gRPC). Agents and other modules that you publish on Naptha are accessible via API.
- [Local Storage](node/storage/db): Naptha Nodes support the deployment of Environment modules, which are things like group chats (think WhatsApp for agents), information boards (Reddit for agents), job boards (LinkedIn for agents), social networks (Twitter for agents), and auctions (eBay for agents). The state of these modules is stored in a local database (postgres) and file system. The Naptha Node also stores details of module runs and (soon) model inference (token usage, costs etc.) in the local database.
- [Module Manager](node/module_manager.py): Supports downloading and installation of modules (agents, tools, agent orchestrators, environments, and personas) from GitHub, HuggingFace and IPFS. 
- [Message Broker and Workers](node/worker/): The Naptha Node uses asynchronous processing and message queues (RabbitMQ) to pass messages between modules. Modules are executed using either Poetry or Docker. 

- (Optional) [Local Hub](node/storage/hub): The Naptha Node can run a local Hub, which is a registry for modules (agents, tools, agent orchestrators, environments, and personas) and nodes by setting LOCAL_HUB=True in the Config. This is useful for testing locally before publishing to the main Naptha Hub. For the Hub DB, we use SurrealDB.


# Install and run

From source:

```bash
git clone https://github.com/NapthaAI/node.git
cd node
```


# Launch the node

There are two ways to launch the node:

1. [Launch with docker compose](READMEs/docker.md)
2. [Launch with systemd/launchd](READMEs/systemd.md)


# Run AI agents on your node

To run agents, keep your node running and follow the instructions using the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk). In the SDK repo, you should set the NODE_URL to the URL of your local node (default is http://localhost:7001).




