import asyncio

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.git_ssh import handle_process, identity_for_fingerprint
from app.security import throttle
from app.ssh_support import ensure_host_key, parse_public_key


def server_factory(library, connections):
    class GitSSHServer(library.SSHServer):
        def connection_made(self, conn):
            self.connection = conn
            connections.add(conn)

        def connection_lost(self, exc):
            connections.discard(self.connection)

        def begin_auth(self, username):
            self.connection.set_extra_info(forge_identity=None)
            return True

        def public_key_auth_supported(self):
            return True

        async def validate_public_key(self, username, key):
            if username != "git":
                return False
            try:
                _, fingerprint = parse_public_key(key.export_public_key("openssh").decode())
                identity = await run_in_threadpool(identity_for_fingerprint, fingerprint)
                if identity is not None:
                    self.connection.set_extra_info(forge_identity=identity)
                    return True
                peer = self.connection.get_extra_info("peername", ("unknown",))[0]
                throttle(f"ssh-auth:{peer}")
            except HTTPException as error:
                if error.status_code == 429:
                    self.connection.close()
            return False

        def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
            return False

        def server_requested(self, listen_host, listen_port):
            return False

        def unix_connection_requested(self, dest_path):
            return False

        def unix_server_requested(self, listen_path):
            return False

    return GitSSHServer


class SSHService:
    def __init__(self, listener, connections):
        self.listener = listener
        self.connections = connections

    async def close(self):
        self.listener.close()
        await self.listener.wait_closed()
        connections = list(self.connections)
        for connection in connections:
            connection.close()
        await asyncio.gather(
            *(connection.wait_closed() for connection in connections), return_exceptions=True
        )


async def start_ssh_server():
    # Import only when enabled: local HTTP development does not start an SSH listener.
    import asyncssh

    config = settings()
    key = ensure_host_key()
    connections = set()
    listener = await asyncssh.create_server(
        server_factory(asyncssh, connections),
        config.ssh_listen_host,
        config.ssh_listen_port,
        server_host_keys=[str(key)],
        process_factory=handle_process,
        encoding=None,
        config=None,
        public_key_auth=True,
        password_auth=False,
        kbdint_auth=False,
        host_based_auth=False,
        gss_auth=False,
        gss_kex=False,
        allow_pty=False,
        agent_forwarding=False,
        x11_forwarding=False,
        allow_scp=False,
        sftp_factory=None,
        login_timeout=30,
        keepalive_interval=30,
        keepalive_count_max=3,
    )
    return SSHService(listener, connections)
