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
         ▀█▄ █  █ █ █ █  ▄█▀               Orchestrating the Decentralized Web of Agents
            ▀█  █ █ █ █ ▌▀                                                 www.naptha.ai
              ▀▀█ █ ██▀▀                                                    
 

# NapthaAI Node  

Naptha helps users to solve real-world problems using AI workflows and agents.

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

This will install all of the components, including:
- Python 3.12 (pre-Requirement)
- Poetry (manages dependencies)
- SurrealDB (Naptha Protocol info is stored here)
- RabbitMQ (message-broker for the Naptha Protocol)
- Ollama (used to run LLMs)
- Docker (isolates agents from the system)
- Naptha node (orchestrates ML workflows)

The first time you launch, you will be prompted about whether (i) to generate a private key, and (ii) to input a Stability API key, which is needed if you would like to run the image agent examples. If you choose not to, you can always edit the .env file manually later.

After a few minutes you should see ```[System] Setup complete. Applications are running.```


Before running agents and multi-agent networks via the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk), you should wait to check that the servers set up correctly by running the following in a new terminal window. On Linux:

```bash
journalctl -u nodeapp_0 -n 100 -f
```

On MacOS:

```bash
tail -n 100 -f /tmp/nodeapp_0.err
```

You should see ```Uvicorn running on http://0.0.0.0:7001```. If you ran with NUM_SERVERS>1, you can check those replacing ```nodeapp_0``` with ```nodeapp_1```, ```nodeapp_2```, etc. That's it! You're now running a local AI node.

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

To run agents, keep your node running and follow the the instructions using the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk). 

# Troubleshooting

If you get an unexpected error when running agents and multi-agent networks, you can check the logs for the servers using the same commands above. You can also check the logs of the workers, which may show an error if you e.g. have a bug in the code you wrote for an agent package. On Linux:

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
