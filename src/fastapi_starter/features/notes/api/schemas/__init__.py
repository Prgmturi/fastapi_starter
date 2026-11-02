"""What the API accepts (request.py) and what it returns (response.py).

Two models, never one for both directions: a client must not be able to
send the fields the server decides, and a response must not carry fields
the client does not need.

The names say the direction: what the client sends ends in Request
(CreateNoteRequest), what it gets back in Response (NoteResponse).
tests/test_main.py checks the names of every route. A feature with several
resources can turn each module into a package: request/note.py,
request/tag.py.
"""
