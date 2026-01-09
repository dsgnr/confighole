# Test configuration constants
PIHOLE_CONTAINER_NAME = "confighole-test"
DOCKER_COMPOSE_FILE = "tests/assets/pihole-docker-compose.yml"
PIHOLE_BASE_URL = "http://localhost:8080"
PIHOLE_TEST_PASSWORD = "test-password-123"
PIHOLE_AUTH_ENDPOINT = "/api/auth"
PIHOLE_AUTH_URL = f"{PIHOLE_BASE_URL}{PIHOLE_AUTH_ENDPOINT}"

# Timeout constants (in seconds)
CONTAINER_STARTUP_TIMEOUT = 60
AUTH_TIMEOUT = 30
REQUEST_TIMEOUT = 5
POLL_INTERVAL = 3
FINAL_WAIT = 5

# HTTP status codes
HTTP_OK = 200

# ConfigHole test constants
TEST_CONFIG_PATH = "tests/assets/test_config.yaml"
TEST_INSTANCE_NAME = "test-instance"
DEFAULT_DAEMON_INTERVAL = 300

# Test DNS configuration
TEST_DNS_UPSTREAMS = ["1.1.1.1", "1.0.0.1"]
TEST_DNS_HOSTS = [
    {"ip": "192.168.1.1", "host": "gateway.test"},
    {"ip": "192.168.1.10", "host": "nas.test"},
]
TEST_DNS_CNAMES = [
    {"name": "plex.test", "target": "nas.test"},
    {"name": "grafana.test", "target": "gateway.test"},
]
