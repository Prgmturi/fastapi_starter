"""What the API accepts (request/) and what it returns (response/).

Two models, never one for both directions: a client must not be able to
send the fields the server decides, and a response must not carry fields
the client does not need.
"""
