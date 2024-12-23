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
		SERVER_TYPE=$$(grep SERVER_TYPE .env | cut -d '=' -f2 | tr -d '"' | tr -d ' ') && \
		for service in $$(systemctl list-units --plain --no-legend --type=service | grep "nodeapp_$$SERVER_TYPE" | grep "loaded" | awk '{print $$1}'); do \
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

# Helper target to check LOCAL_HUB value from config.py
check-local-hub:
	@echo "Checking LOCAL_HUB setting..."
	@$(PYTHON) -c 'import sys; sys.path.append("."); from node.config import LOCAL_HUB; print("true" if LOCAL_HUB else "false")' > .hub_setting

# Target to restart hub if LOCAL_HUB is True
restart-hub:
	@if [ "$$(cat .hub_setting)" = "true" ]; then \
		echo "LOCAL_HUB is True, restarting hub..."; \
		PYTHONPATH=$$(pwd) poetry run python node/storage/hub/init_hub.py; \
		PYTHONPATH=$$(pwd) poetry run python node/storage/hub/init_hub.py --user; \
		echo "Hub restarted successfully."; \
	else \
		echo "LOCAL_HUB is False, skipping hub restart."; \
	fi
	@rm -f .hub_setting

# Updated restart-node target
restart-node:
	@echo "Restarting all components in parallel..."
	@$(MAKE) remove
	@echo ".venv removed"
	@$(MAKE) pyproject-clean
	@poetry lock
	@poetry install
	@echo "poetry install done"
	@$(MAKE) check-local-hub
	@$(MAKE) restart-hub
	@$(MAKE) restart-servers & $(MAKE) restart-celery
	@wait
	@echo "All node components have been restarted."