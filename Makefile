.PHONY: clean check format pyproject-clean install-toml

# Your Python interpreter (change if needed, e.g., to a virtual environment path)
PYTHON = python

# Path to your pyproject.toml
CURRENT_DIR = $(shell pwd)
# Echo the current directory
PYPROJECT_PATH = $(CURRENT_DIR)/pyproject.toml

# Target to install toml package
install-toml:
	@echo "Installing toml package..."
	@$(PYTHON) -m pip install toml

# Target to clean up pyproject.toml by removing dependencies with local paths
pyproject-clean: install-toml
	@echo "Cleaning pyproject.toml..."
	@$(PYTHON) clean_pyproject.py $(PYPROJECT_PATH)

# Target to run ruff check
check:
	@echo "Running ruff check..."
	@ruff check

# Target to run ruff format
format:
	@echo "Running ruff format..."
	@ruff format

# Target to clean using ruff
clean:
	@echo "Cleaning with ruff..."
	@ruff clean

# Combines all the cleaning operations
all-clean: clean check format pyproject-clean
	@echo "All clean operations done."

# Target to remove __pycache__, .venv, and node/storage/hub/modules
remove:
	@echo "Removing __pycache__, .venv, and node/storage/hub/modules..."
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@rm -rf .venv
	@rm -rf node/storage/hub/modules
	@echo "Cleanup completed."

# Target to remove hub.db
remove-hub:
	@echo "Removing hub.db"
	cd $(shell pwd) && \
	hub_path=$$PWD/node/storage/hub/hub.db && \
	rm -rf $$db_path $$hub_path

# Reset database completely
local-db-reset:
	@echo "Resetting database state..."
	@PYTHONPATH=$(shell pwd) poetry run python node/storage/db/reset_db.py
	@echo "Database reset completed."

local-db-hard-reset:
	@echo "Removing PostgreSQL..."
	@make local-db-reset
	@if [ "$$(uname)" = "Darwin" ]; then \
		brew services stop postgresql@17 || true; \
		brew uninstall postgresql@17 --force || true; \
		brew uninstall pgvector --force || true; \
		rm -rf /opt/homebrew/var/postgresql@17; \
		rm -rf ~/Library/LaunchAgents/homebrew.mxcl.postgresql@17.plist; \
	else \
		sudo systemctl stop postgresql || true; \
		sudo apt-get remove --purge -y postgresql* || true; \
		sudo apt-get remove --purge -y postgresql-16-pgvector || true; \
		sudo apt-get autoremove -y; \
		sudo rm -rf /etc/postgresql/; \
		sudo rm -rf /var/lib/postgresql/; \
		sudo rm -rf /var/log/postgresql/; \
		sudo userdel -r postgres || true; \
		sudo groupdel postgres || true; \
	fi
	@echo "PostgreSQL removed completely."

# Target to restart HTTP server
restart-http:
	@echo "Restarting HTTP server..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		(launchctl unload ~/Library/LaunchAgents/com.example.nodeapp.http.plist && \
		sleep 2 && \
		launchctl load ~/Library/LaunchAgents/com.example.nodeapp.http.plist) & \
	else \
		(sudo systemctl restart nodeapp_http.service && \
		sudo systemctl status nodeapp_http.service) & \
	fi

# Target to restart secondary servers
restart-servers:
	@echo "Restarting secondary servers..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		for plist in $$(ls ~/Library/LaunchAgents/com.example.nodeapp.*.plist); do \
			echo "Unloading $$plist" && \
			(launchctl unload $$plist && \
			sleep 2 && \
			launchctl load $$plist) & \
		done; \
	else \
		NODE_COMMUNICATION_PROTOCOL=$$(grep NODE_COMMUNICATION_PROTOCOL .env | cut -d '=' -f2 | tr -d '"' | tr -d ' ') && \
		for service in $$(systemctl list-units --plain --no-legend --type=service | grep "nodeapp_$$NODE_COMMUNICATION_PROTOCOL" | grep "loaded" | awk '{print $$1}'); do \
			if systemctl is-active --quiet $$service; then \
				(echo "Restarting $$service" && \
				sudo systemctl restart $$service && \
				sudo systemctl status --no-pager $$service) & \
			fi \
		done; \
	fi
	@wait
	@echo "Secondary servers restarted."

# Target to restart Celery
restart-celery:
	@echo "Restarting Celery worker..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		(launchctl unload ~/Library/LaunchAgents/com.example.celeryworker.plist && \
		sleep 2 && \
		launchctl load ~/Library/LaunchAgents/com.example.celeryworker.plist) & \
	else \
		(sudo systemctl restart celeryworker.service && \
		sudo systemctl status --no-pager celeryworker.service) & \
	fi

check-local-hub:
	@echo "Checking LOCAL_HUB setting..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		grep -E '^LOCAL_HUB=' .env | cut -d'=' -f2 | tr -d '"' | tr -d ' ' > .hub_setting; \
	else \
		grep -oP 'LOCAL_HUB=\K.*' .env | tr -d '"' | tr -d ' ' > .hub_setting; \
	fi
	@echo "LOCAL_HUB is $$(cat .hub_setting)"

restart-hub: check-local-hub
	@{ \
	  if [ "$$(cat .hub_setting)" = "true" ]; then \
	    echo "LOCAL_HUB is True, cleaning and restarting hub..."; \
	    port=$$(grep HUB_DB_SURREAL_PORT .env | cut -d'=' -f2 | tr -d '"' | tr -d ' '); \
	    echo "Port is $$port"; \
	    pids=$$(lsof -ti:$$port || true); \
	    if [ -n "$$pids" ]; then \
	      echo "Killing process(es): $$pids"; \
	      kill -9 $$pids || true; \
	    fi; \
	    echo "Waiting for port $$port to be free..."; \
	    for i in $$(seq 1 10); do \
	      if ! lsof -ti:$$port 2>/dev/null | grep -q .; then \
	        echo "Port $$port is now free"; \
	        break; \
	      fi; \
	      if [ $$i -eq 10 ]; then \
	        echo "Failed to free port $$port after 10 seconds"; \
	        exit 1; \
	      fi; \
	      echo "Still waiting... ($$i/10)"; \
	      sleep 1; \
	    done; \
	    if [ -d "node/storage/hub/hub.db" ]; then \
	      rm -rf node/storage/hub/hub.db; \
		  echo "Hub.db removed"; \
	    fi; \
	    PYTHONPATH="$$(pwd)" poetry run python node/storage/hub/init_hub.py; \
	    PYTHONPATH="$$(pwd)" poetry run python node/storage/hub/init_hub.py --user; \
	    echo "Hub restarted successfully."; \
	  else \
	    echo "LOCAL_HUB is False, skipping hub restart."; \
	  fi; \
	}
	@rm -f .hub_setting

# Target to restart all node components in parallel
restart-node:
	@echo "Restarting all components in parallel..."
	@$(MAKE) remove
	@echo ".venv removed"
	@$(MAKE) pyproject-clean
	@poetry lock
	@poetry install
	@echo "poetry install done"
	@$(MAKE) restart-hub
	@$(MAKE) restart-servers & $(MAKE) restart-celery
	@wait
	@echo "All node components have been restarted."
