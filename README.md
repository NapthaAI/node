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
bash launch.sh
```

This will install all of the required components. After a few minutes you should see,```[System] Setup complete. Applications are running.```

Then, in a new window run:

```bash
journalctl -u nodeapp -n 100 -f
```

That's it! You're now running a local AI node.

# Set up your payment settings

Coming soon.

# Run AI modules on your node

To run modules, keep your node running and follow the the instructions using the [Naptha SDK](https://github.com/NapthaAI/naptha-sdk). 


## Stop

```
bash stop-service.sh
```