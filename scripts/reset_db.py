from node.config import LOCAL_DB_NAME, LOCAL_DB_USER, LOCAL_DB_PASSWORD, LOCAL_DB_PORT
import subprocess
import platform
import sys

def reset_db():
    print("Starting database reset...")
    
    is_macos = platform.system() == 'Darwin'
    
    if is_macos:
        commands = [
            f"psql -p {LOCAL_DB_PORT} postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{LOCAL_DB_NAME}' AND pid <> pg_backend_pid();\"",
            f"dropdb -p {LOCAL_DB_PORT} --if-exists {LOCAL_DB_NAME}",
            f"dropuser -p {LOCAL_DB_PORT} --if-exists {LOCAL_DB_USER}",
            f"createuser -p {LOCAL_DB_PORT} {LOCAL_DB_USER}",
            f"psql -p {LOCAL_DB_PORT} postgres -c \"ALTER USER {LOCAL_DB_USER} WITH PASSWORD '{LOCAL_DB_PASSWORD}';\"",
            f"createdb -p {LOCAL_DB_PORT} --owner={LOCAL_DB_USER} {LOCAL_DB_NAME}",
            f"psql -p {LOCAL_DB_PORT} postgres -c \"ALTER USER {LOCAL_DB_USER} CREATEDB;\""
        ]
    else:
        commands = [
            f"sudo -u postgres psql -d template1 -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{LOCAL_DB_NAME}' AND pid <> pg_backend_pid();\"",
            f"sudo -u postgres psql -d template1 -c \"DROP DATABASE IF EXISTS {LOCAL_DB_NAME};\"",
            f"sudo -u postgres psql -d template1 -c \"DROP USER IF EXISTS {LOCAL_DB_USER};\"",
            f"sudo -u postgres psql -d template1 -c \"CREATE USER {LOCAL_DB_USER} WITH PASSWORD '{LOCAL_DB_PASSWORD}';\"",
            f"sudo -u postgres psql -d template1 -c \"CREATE DATABASE {LOCAL_DB_NAME} WITH OWNER {LOCAL_DB_USER};\"",
            f"sudo -u postgres psql -d template1 -c \"ALTER USER {LOCAL_DB_USER} CREATEDB;\""
        ]

    print("Executing database commands...")
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"✓ {cmd}")
        except subprocess.CalledProcessError as e:
            print(f"\nError executing: {cmd}")
            print(f"Exit code: {e.returncode}")
            if e.stdout:
                print(f"stdout: {e.stdout}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
            sys.exit(1)

    print("Database reset complete!")

if __name__ == "__main__":
    reset_db()