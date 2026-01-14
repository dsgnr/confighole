"""Test fixtures and setup for ConfigHole."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import docker
import docker.errors
import pytest
import requests
from pihole_lib import PiHoleClient

from tests.constants import (
    AUTH_TIMEOUT,
    CONTAINER_STARTUP_TIMEOUT,
    DOCKER_COMPOSE_FILE,
    HTTP_OK,
    PIHOLE_AUTH_URL,
    PIHOLE_BASE_URL,
    PIHOLE_CONTAINER_NAME,
    PIHOLE_TEST_PASSWORD,
    POLL_INTERVAL,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
)

if TYPE_CHECKING:
    pass


def is_pihole_ready() -> bool:
    """Check if Pi-hole API is ready and accepting connections."""
    try:
        response = requests.post(
            PIHOLE_AUTH_URL,
            json={"password": PIHOLE_TEST_PASSWORD},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            return data.get("session", {}).get("valid", False)
    except Exception:
        pass
    return False


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def docker_compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["docker-compose", "-f", DOCKER_COMPOSE_FILE, *args],
        cwd=project_root(),
        check=check,
        capture_output=True,
        text=True,
    )
    return result


def wait_for_container_health(container) -> None:
    """Block until the Docker container becomes healthy."""
    elapsed = 0

    while elapsed < CONTAINER_STARTUP_TIMEOUT:
        container.reload()
        health = container.attrs.get("State", {}).get("Health", {})
        status = health.get("Status", "unknown")

        if status == "healthy":
            return

        if status == "unhealthy":
            logs = container.logs().decode()
            pytest.fail(f"Container became unhealthy:\n{logs}")

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    logs = container.logs().decode()
    pytest.fail(
        f"Container did not become healthy within {CONTAINER_STARTUP_TIMEOUT}s:\n{logs}"
    )


def is_dns_ready(client) -> bool:
    """Check if Pi-hole DNS service is ready."""
    try:
        from pihole_lib import PiHoleInfo

        info = PiHoleInfo(client)
        return info.get_login_info().dns
    except Exception:
        return False


def wait_for_pihole_restart(client, timeout: int = 120) -> None:
    """Wait for Pi-hole to restart and DNS to become available again."""

    time.sleep(RETRY_DELAY)  # allow restart to begin
    start = time.time()

    while time.time() - start < timeout:
        try:
            temp_client = PiHoleClient(
                base_url=PIHOLE_BASE_URL,
                password=PIHOLE_TEST_PASSWORD,
                verify_ssl=False,
                timeout=10,
            )

            if is_dns_ready(temp_client):
                temp_client.close()

                # Reset original client session (restart invalidates it)
                client._session_id = None
                if client._session:
                    client._session.close()
                    client._session = None

                time.sleep(RETRY_DELAY)
                return

            temp_client.close()

        except Exception:
            pass  # expected during restart window

        time.sleep(RETRY_DELAY)

    raise RuntimeError(f"Pi-hole did not restart within {timeout} seconds")


@pytest.fixture
def pihole_restart_isolation(pihole_container):
    """Ensure spacing between tests that restart Pi-hole."""
    yield
    time.sleep(5)


@pytest.fixture(scope="session")
def docker_client() -> Iterator[docker.DockerClient]:
    """Provide a Docker client."""
    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def pihole_container(docker_client):
    """Start and manage the Pi-hole Docker container."""
    # if we are running in a CI like GitHub Actions,
    # we should assume we are using a service container.
    if os.getenv("IS_CI"):
        yield None
        return

    try:
        try:
            container = docker_client.containers.get(PIHOLE_CONTAINER_NAME)
            if container.status != "running":
                container.start()
        except docker.errors.NotFound:
            docker_compose("up", "-d")
            container = docker_client.containers.get(PIHOLE_CONTAINER_NAME)

        wait_for_container_health(container)
        yield container

    finally:
        docker_compose("down", check=False)


@pytest.fixture(scope="session")
def pihole_session(pihole_container):
    """Create a shared PiHoleClient for integration tests.

    This fixture creates a single PiHoleClient instance that is reused
    across all integration tests in the session, avoiding connection
    reset errors from creating too many sessions.
    """

    client = PiHoleClient(
        base_url=PIHOLE_AUTH_URL,
        password=PIHOLE_TEST_PASSWORD,
        verify_ssl=False,
        timeout=AUTH_TIMEOUT,
    )

    yield client

    client.close()
