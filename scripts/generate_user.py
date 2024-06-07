#!/usr/bin/env python
from node.user import generate_user

public_key, private_key = generate_user()

print(private_key)
