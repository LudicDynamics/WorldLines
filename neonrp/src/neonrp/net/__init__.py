"""The network layer: headless = the host process, the one truth of
the world; everyone else — the TUI, the web test bench, remote characters and players, other people's AIs — is a client.

- ``protocol``  JSON-RPC 2.0 envelope + the thin session layer (version handshake, seq, server→client requests)
- ``host``      the host side, mounted on the engine's HTTP server (``neonrp serve``): POST /rpc · GET /rpc/events (SSE)
- ``client``    ``EngineClient``: one interface, two implementations — in-process (today's behaviour) and remote
"""
