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
         ▀█▄ █  █ █ █ █  ▄█▀                         Decentralized Multi-Agent Workflows
            ▀█  █ █ █ █ ▌▀                                                 www.naptha.ai
              ▀▀█ █ ██▀▀                                                    
 

# NapthaAI Node  

Naptha helps users to solve real-world problems using AI workflows and agents.

# Install and run

From source:

```bash
git clone https://github.com/NapthaAI/node.git
cd node
```

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
- Docker (isolates Modules from the system)
- Naptha node (orchestrates ML workflows)

The first time you launch, you will be prompted about whether (i) to generate a private key, and (ii) to input a Stability API key, which is needed if you would like to run the image module examples. If you choose not to, you can always edit the .env file manually later.

After a few minutes you should see,```[System] Setup complete. Applications are running.```

Then, in a new terminal window run:

On Linux:

```bash
journalctl -u nodeapp -n 100 -f
```

On MacOS:

```bash
tail -n 100 -f /tmp/nodeapp.err
```

That's it! You're now running a local AI node.

# Run AI modules on your node

To run modules, keep your node running and follow the the instructions using the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk). 

# Set up your payment settings

Coming soon.

## Stop

```
bash stop-service.sh
```

## To cleanup

```
make remove
```
