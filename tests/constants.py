"""Test configuration constants."""

# Pi-hole container settings
PIHOLE_CONTAINER_NAME = "confighole-test"
DOCKER_COMPOSE_FILE = "tests/assets/pihole-docker-compose.yml"
PIHOLE_BASE_URL = "http://localhost:8080"
PIHOLE_TEST_PASSWORD = "test-password-123"
PIHOLE_AUTH_ENDPOINT = "/api/auth"
PIHOLE_AUTH_URL = f"{PIHOLE_BASE_URL}{PIHOLE_AUTH_ENDPOINT}"

# Timeout constants (seconds)
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

# Sample DNS configuration for tests
SAMPLE_DNS_UPSTREAMS = ["1.1.1.1", "1.0.0.1"]
SAMPLE_DNS_HOSTS = [
    {"ip": "192.168.1.1", "host": "gateway.test"},
    {"ip": "192.168.1.10", "host": "nas.test"},
]
SAMPLE_DNS_CNAMES = [
    {"name": "plex.test", "target": "nas.test"},
    {"name": "grafana.test", "target": "gateway.test"},
]

# Sample list configuration for tests
SAMPLE_LIST = {
    "address": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
    "type": "block",
    "comment": "Migrated from /etc/pihole/adlists.list",
    "groups": [0],
    "enabled": True,
}

# Sample domain configuration for tests
SAMPLE_DOMAIN = {
    "domain": "blocked.example.com",
    "type": "deny",
    "kind": "exact",
    "comment": "Test domain",
    "groups": [0],
    "enabled": True,
}

SAMPLE_DOMAIN_REGEX = {
    "domain": r".*\.ads\..*",
    "type": "deny",
    "kind": "regex",
    "comment": "Block ads subdomains",
    "groups": [0],
    "enabled": True,
}

# Sample group configuration for tests
SAMPLE_GROUP = {
    "name": "test-group",
    "comment": "Test group",
    "enabled": True,
}
