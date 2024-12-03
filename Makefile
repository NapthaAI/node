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
	@python3 scripts/reset_db.py
	@echo "Database reset completed. Ready for init_db.py to be executed by launch.sh"