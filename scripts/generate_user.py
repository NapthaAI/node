#!/usr/bin/env python
from node.user import generate_user

public_key, pem_file = generate_user()
print(pem_file)
