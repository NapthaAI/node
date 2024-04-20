             %
             %%
             %%#
             %-+%
           %%%+.#
         #%#%.*=-%#
       #%=.%+-*%-:%%
      %%#*.*.#--%--*=%
     #%*%*.*.+- +-:%*%#     ███╗   ██╗ █████╗ ██████╗ ████████╗██╗  ██╗ █████╗ 
    #@:= *.%::#+:%%.=.%#    ████╗  ██║██╔══██╗██╔══██╗╚══██╔══╝██║  ██║██╔══██╗
     %%:*#.#*:*%=:*:=%%     ██╔██╗ ██║███████║██████╔╝   ██║   ███████║███████║
      %*-*:..=-%*:*:##      ██║╚██╗██║██╔══██║██╔═══╝    ██║   ██╔══██║██╔══██║
       ##+*--+-%=#+##       ██║ ╚████║██║  ██║██║        ██║   ██║  ██║██║  ██║
        #%#+=+=%*%%#        ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝        ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
          #%#%#%%#                             Decentralized Task Orchestration   
                                                                  www.naptha.ai

# NapthaAI Node  

Naptha helps users to solve real-world problems using AI workflows and agents.

# Install and run

From source:

```bash
git clone https://github.com/NapthaAI/node.git
cd node
```

Copy the env file (and add a valid Stability platform API key, if you would like to use the image modules):

```bash
cp .env.example .env
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

 After a few minutes you should see,```[System] Setup complete. Applications are running.```

Then, in a new terminal window run:

```bash
journalctl -u nodeapp -n 100 -f
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