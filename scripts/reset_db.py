from node.config import LOCAL_DB_NAME, LOCAL_DB_USER, LOCAL_DB_PASSWORD
import subprocess

def reset_db():
    commands = [
        f"sudo -u postgres psql -d template1 -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{LOCAL_DB_NAME}' AND pid <> pg_backend_pid();\"",
        f"sudo -u postgres psql -d template1 -c \"DROP DATABASE IF EXISTS {LOCAL_DB_NAME};\"",
        f"sudo -u postgres psql -d template1 -c \"DROP USER IF EXISTS {LOCAL_DB_USER};\"",
        f"sudo -u postgres psql -d template1 -c \"CREATE USER {LOCAL_DB_USER} WITH PASSWORD '{LOCAL_DB_PASSWORD}';\"",
        f"sudo -u postgres psql -d template1 -c \"CREATE DATABASE {LOCAL_DB_NAME} WITH OWNER {LOCAL_DB_USER};\"",
        f"sudo -u postgres psql -d template1 -c \"ALTER USER {LOCAL_DB_USER} CREATEDB;\""
    ]
    
    for cmd in commands:
        subprocess.run(cmd, shell=True, check=True)

if __name__ == "__main__":
    reset_db()