#!/usr/bin/env python
from node.user import generate_user
import sys

if __name__ == "__main__":
    # get username from command line
    username = sys.argv[1]
    public_key, pem_file = generate_user(username)
    print(pem_file)
