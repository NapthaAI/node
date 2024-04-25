"""
Clean pyproject.toml file from path dependencies
"""

import toml
import sys


def remove_path_dependencies(pyproject_path):
    with open(pyproject_path, "r") as file:
        data = toml.load(file)
    dependencies = data["tool"]["poetry"]["dependencies"]
    for key in list(dependencies.keys()):
        if isinstance(dependencies[key], dict) and "path" in dependencies[key]:
            del dependencies[key]
    with open(pyproject_path, "w") as file:
        toml.dump(data, file)


if __name__ == "__main__":
    pyproject_path = sys.argv[1]
    remove_path_dependencies(pyproject_path)
