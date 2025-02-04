# Setting up your Naptha Node with systemd/launchd

The Naptha Node can be run using systemd/launchd services. This is closer to metal than using docker compose, and is useful if you want to run the node on a server.

## Configuring your Naptha Node

- `LAUNCH_DOCKER`: Set to False if you want to launch the node using systemd/launchd.
- `LLM_BACKEND`: Should be set to "ollama" if using systemd/launchd. If you want to use VLLM, you should launch using docker compose by following the instructions in the [Docker](READMEs/docker.md) guide.
- `OLLAMA_MODELS`: Set this to the models you want to use, separated by commas. By default, the node will use the Nous Research Hermes 3 model.

For advanced configuration settings, see the [Advanced Configuration](READMEs/advanced.md) guide.

## Launching the Naptha Node

Then run the node:

```bash
bash launch.sh
```

The first time you launch, you will be prompted about whether (i) to generate a private key, and (ii) to input a Stability API key, which is needed if you would like to run the image agent examples. If you choose not to, you can always edit the .env file manually later.

After a few minutes you should see a table of the status of the services, something like this:

```
[Summary] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Summary]            🔍 SERVICE STATUS              
[Summary] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Summary]                                          
[Summary]   PostgreSQL           ✅
[Summary]   Hub DB               ✅
[Summary]   Celery               ✅
[Summary]   HTTP Server          ✅
[Summary]   WS Server 7002       ✅
[Summary]   LiteLLM              ✅
[Summary]                                          
[Summary] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Summary] 
[Summary] ✨ All services started successfully!
[System] Setup complete. Applications are running.
```

All of the services should have a status of ✅, which means that they have started successfully.

## Troubleshooting

If any of the services have a status of ❌, you can check the logs for the service using the following commands:

On Linux:

```bash
journalctl -u <service_name>.service -n 1000 -f
```

On MacOS:

```bash
tail -n 1000 -f /tmp/<service_name>.log
```

where `<service_name>` is the name of the service you want to check the logs for. 

1. `nodeapp_http` is the HTTP server.
2. `nodeapp_ws_7002` is the Web Socket server (logs of other node communication servers use `nodeapp_ws_<port>`).
3. `celeryworker` is the Celery worker.
4. `litellm` is the LiteLLM proxy server.

You can also check the logs if you get an unexplained error when running agents and other modules. If there is a bug in the code of the module, it will usually show up in the `celeryworker` logs. If there is an issue with the input schema, it will usually show up in the `nodeapp_http` logs.


## Stopping the Naptha Node

```
bash stop_service.sh
```

## Resetting the Naptha Node

### Removing the node and module environments

If you are having dependency or version issues, you may want to remove the node and module environments by running:

```
make remove
```

Cleans up by removing:
   - All `__pycache__` directories
   - `.venv` virtual environment directory 
   - `node/storage/hub/modules` directory

### Resetting the databases

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

## Restarting the Naptha Node

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
