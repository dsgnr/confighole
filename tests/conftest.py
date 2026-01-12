"""Test fixtures and setup for ConfigHole."""

from __future__ import annotations

import os
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
import requests

from tests.constants import (
    AUTH_TIMEOUT,
    CONTAINER_STARTUP_TIMEOUT,
    DOCKER_COMPOSE_FILE,
    FINAL_WAIT,
    HTTP_OK,
    PIHOLE_AUTH_URL,
    PIHOLE_TEST_PASSWORD,
    POLL_INTERVAL,
    REQUEST_TIMEOUT,
)

if TYPE_CHECKING:
    from collections.abc import Generator


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


def get_project_dir() -> str:
    """Get the project root directory."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(test_dir)


def cleanup_container() -> None:
    """Stop and remove the Pi-hole test container."""
    try:
        print("Cleaning up Pi-hole test container...")
        subprocess.run(
            ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "down", "-v"],
            cwd=get_project_dir(),
            check=False,
            capture_output=True,
        )
        print("Pi-hole test container cleaned up")
    except Exception as e:
        print(f"Warning: Container cleanup failed: {e}")


@pytest.fixture(scope="session")
def pihole_container() -> Generator[str, None, None]:
    """Ensure Pi-hole container is running for integration tests."""
    project_dir = get_project_dir()

    # Check if already running
    if is_pihole_ready():
        yield "pihole-test"
        cleanup_container()
        return

    # Start the container
    try:
        subprocess.run(
            ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "up", "-d"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        # Wait for Pi-hole to be ready
        elapsed = 0
        while elapsed < CONTAINER_STARTUP_TIMEOUT:
            if is_pihole_ready():
                time.sleep(FINAL_WAIT)
                yield "pihole-test"
                cleanup_container()
                return

            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        cleanup_container()
        pytest.fail(f"Pi-hole failed to start within {CONTAINER_STARTUP_TIMEOUT}s")

    except subprocess.CalledProcessError as e:
        cleanup_container()
        pytest.skip(f"Failed to start Pi-hole container: {e}")

    except Exception:
        cleanup_container()
        raise


@pytest.fixture(scope="session")
def pihole_session(
    pihole_container: str,
) -> Generator[tuple[requests.Session, str], None, None]:
    """Create a reusable authenticated Pi-hole session."""
    _ = pihole_container

    session = requests.Session()
    session.verify = False

    response = session.post(
        PIHOLE_AUTH_URL,
        json={"password": PIHOLE_TEST_PASSWORD},
        timeout=AUTH_TIMEOUT,
    )

    if response.status_code != HTTP_OK:
        pytest.fail(f"Authentication failed: {response.status_code}")

    data = response.json()
    session_info = data.get("session", {})

    if not session_info.get("valid"):
        pytest.fail("Authentication failed - invalid session")

    session_id = session_info.get("sid")
    if not session_id:
        pytest.fail("No session ID received")

    session.headers.update({"X-FTL-SID": session_id})

    yield session, session_id

    try:
        session.delete(PIHOLE_AUTH_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        pass
    finally:
        session.close()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up after all tests complete."""
    cleanup_container()


def pytest_keyboard_interrupt(excinfo: BaseException) -> None:
    """Clean up when tests are interrupted."""
    print("\nInterrupt: Cleaning up...")
    cleanup_container()
