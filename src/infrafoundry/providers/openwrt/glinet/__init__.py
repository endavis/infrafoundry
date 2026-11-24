"""GL.iNet web-API support for the OpenWrt provider (ADR-0036).

``settings`` reads the web credentials and certificate pin, ``rpc`` is the pinned
JSON-RPC client, ``crypt`` reproduces the login challenge's password hash, ``firmware``
checks for and installs the vendor's latest release, and ``cli`` is
``foundry provider openwrt upgrade``.
"""
