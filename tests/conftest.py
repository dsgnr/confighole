"""Test setup and fixtures for ConfigHole."""

import os
import subprocess
import time

import pytest
import requests

from .constants import (
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


def is_pihole_ready() -> bool:
    """Check if Pi-hole API is ready."""
    try:
        # Test authentication
        auth_response = requests.post(
            PIHOLE_AUTH_URL,
            json={"password": PIHOLE_TEST_PASSWORD},
            timeout=REQUEST_TIMEOUT,
        )
        if auth_response.status_code == HTTP_OK:
            auth_data = auth_response.json()
            return auth_data.get("session", {}).get("valid", False)
        return False
    except Exception:
        return False


@pytest.fixture(scope="session")
def pihole_container():
    """Ensure Pi-hole container is running for testing."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(test_dir)

    def cleanup_container():
        """Cleanup function to ensure container is always removed."""
        try:
            print("Cleaning up Pi-hole test container...")
            subprocess.run(
                ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "down", "-v"],
                cwd=project_dir,
                check=False,
                capture_output=True,
            )
            print("Pi-hole test container cleaned up successfully")
        except Exception as e:
            print(f"Warning: Failed to clean up Docker container: {e}")

    # Check if Pi-hole is already accessible
    if is_pihole_ready():
        yield "pihole-test"
        # Always cleanup after tests, even if container was already running
        cleanup_container()
        return

    # Try to start the container if it's not running
    try:
        # Start container with docker-compose
        subprocess.run(
            ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "up", "-d"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        # Wait for Pi-hole to be ready
        max_wait = CONTAINER_STARTUP_TIMEOUT
        wait_time = 0

        while wait_time < max_wait:
            if is_pihole_ready():
                # Give it more time to fully initialise
                time.sleep(FINAL_WAIT)
                yield "pihole-test"
                # Cleanup after tests complete
                cleanup_container()
                return

            time.sleep(POLL_INTERVAL)
            wait_time += POLL_INTERVAL

        # If we get here, Pi-hole failed to start
        cleanup_container()  # Clean up failed container
        pytest.fail(f"Pi-hole API failed to start within {max_wait}s")

    except subprocess.CalledProcessError as e:
        cleanup_container()  # Clean up on error
        pytest.skip(f"Failed to start Pi-hole container: {e}")
    except Exception:
        cleanup_container()  # Clean up on any other error
        raise


@pytest.fixture(scope="session")
def pihole_session(pihole_container):
    """Create a reusable Pi-hole session to avoid rate limiting."""
    # Wait for the container to be ready first
    _ = pihole_container

    session = requests.Session()
    session.verify = False

    # Authenticate once for the entire test session
    auth_response = session.post(
        PIHOLE_AUTH_URL,
        json={"password": PIHOLE_TEST_PASSWORD},
        timeout=AUTH_TIMEOUT,
    )

    if auth_response.status_code != HTTP_OK:
        pytest.fail(f"Failed to authenticate: {auth_response.status_code}")

    auth_data = auth_response.json()
    session_info = auth_data.get("session", {})

    if not session_info.get("valid"):
        pytest.fail("Authentication failed - invalid session")

    session_id = session_info.get("sid")
    if not session_id:
        pytest.fail("No session ID received")

    # Store session ID for cleanup
    session.headers.update({"X-FTL-SID": session_id})

    yield session, session_id

    # Clean up session
    try:
        session.delete(PIHOLE_AUTH_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        pass
    finally:
        session.close()


def pytest_sessionfinish(session, exitstatus):
    """Cleanup function that runs at the end of the test session."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(test_dir)

    try:
        print("Final cleanup: Stopping Pi-hole test container...")
        subprocess.run(
            ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "down", "-v"],
            cwd=project_dir,
            check=False,
            capture_output=True,
        )
        print("Final cleanup completed")
    except Exception as e:
        print(f"Warning: Final cleanup failed: {e}")


def pytest_keyboard_interrupt(excinfo):
    """Cleanup function that runs when tests are interrupted with Ctrl+C."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(test_dir)

    try:
        print("\nInterrupt cleanup: Stopping Pi-hole test container...")
        subprocess.run(
            ["docker-compose", "-f", DOCKER_COMPOSE_FILE, "down", "-v"],
            cwd=project_dir,
            check=False,
        )
        print("Interrupt cleanup completed")
    except Exception as e:
        print(f"Warning: Interrupt cleanup failed: {e}")
