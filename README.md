# ConfigHole

**Pi-hole configuration as code.**

ConfigHole is a small tool for managing one or more Pi-hole instances from a single YAML file. It is aimed at homelabs and self-hosted setups where you want your DNS configuration to be repeatable, reviewable, and easy to keep in sync.

It is built on top of another project of mine, [pihole-lib](https://github.com/dsgnr/pihole-lib), a Python library that talks to the Pi-hole API.

## Table of Contents

- [Disclaimer](#disclaimer)
- [Supported Pi-hole Versions](#supported-pi-hole-versions)
- [Features](#features)
- [TODO](#todo)
- [Installation](#installation)
- [Usage](#usage)
- [Daemon Mode](#daemon-mode)
- [Configuration](#configuration)
- [Development](#development)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Pi-hole LLC. Pi-hole is a trademark of Pi-hole LLC.

ConfigHole was written for my own homelab to keep Pi-hole configuration under version control and in sync (I use Flux to manage my Kubernetes clusters). It is a personal tool that escaped into a public repository, and it is built for homelabs rather than production environments.

It works for me, but it may not work for you. There are no warranties, no guarantees, and no promises that it will not break your DNS at an inconvenient moment. 

Read the code, test your changes, and use dry-run mode before trusting it with anything important.

## Supported Pi-hole Versions

Designed and tested against Pi-hole **v6.0 and newer**.

## Features

- Manage Pi-hole configuration declaratively using YAML
- Keep multiple Pi-hole instances in sync
- Manage blocklists and allowlists
- Manage domains (exact and regex, allow and deny)
- Manage groups
- Manage clients
- Optional automatic gravity update when lists change
- See exactly what will change before applying it
- Dry-run mode so you can test without touching anything
- Optional daemon mode for periodic reconciliation

## Installation

### Docker

> [!NOTE]
> Example docker-compose file can be found at [examples/docker-compose.yaml](examples/docker-compose.yaml):

```bash
# One-time sync
$ docker run --rm \
  -v $(pwd)/config:/config:ro \
  -e PIHOLE_PASSWORD="$PIHOLE_PASSWORD" \
  ghcr.io/dsgnr/confighole:latest -c config/config.yaml --sync

# Run daemon
$ docker run -d --name confighole-daemon \
  --restart unless-stopped \
  -v $(pwd)/config:/config:ro \
  -e CONFIGHOLE_DAEMON_MODE=true \
  -e CONFIGHOLE_CONFIG_PATH=/config/config.yaml \
  -e CONFIGHOLE_DAEMON_INTERVAL=300 \
  -e PIHOLE_PASSWORD="$PIHOLE_PASSWORD" \
  ghcr.io/dsgnr/confighole:latest
```

### Python

> [!NOTE]
> Uses Python 3.13. The Python environment uses [Poetry](https://pypi.org/project/poetry/) for package management. This must be installed.

```bash
$ git clone https://github.com/dsgnr/confighole.git
$ cd confighole
$ poetry install
$ poetry run confighole --help
```

## Usage

Create a `config.yaml` - An example can be seen at [examples/config.yaml](examples/config.yaml).

```yaml
# Global settings applied to all instances
global:
  timeout: 30
  verify_ssl: false
  verbosity: 1              # Log verbosity: 0=WARNING, 1=INFO, 2=DEBUG
  dry_run: false            # Enable dry-run

  # Daemon mode settings
  daemon_mode: false        # Enable daemon mode by default
  daemon_interval: 300      # Sync interval in seconds (5 minutes)

instances:
  - name: home
    base_url: http://192.168.1.100
    password: "${PIHOLE_PASSWORD}"
    config:
      dns:
        upstreams: ["1.1.1.1", "1.0.0.1"]
        queryLogging: true
        dnssec: true
        hosts:
          - ip: 192.168.1.1
            host: router.lan
          - ip: 192.168.1.10
            host: nas.lan
        cnameRecords:
          - name: plex.lan
            target: nas.lan
```

> [!TIP]
> YAML anchors work with the config, so you can define a list of hosts/cnames once, and reference them for all instances. For example:
> ``` yaml
>  hosts: &hosts
>   - ip: 192.168.1.1
>     host: gateway.lab
>   - ip: 192.168.1.10
>     host: nas.lab
>
> lists: &lists
>   - address: https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts
>     type: deny
>     comment: StevenBlack's Unified Hosts List
>     groups: [0]
>     enabled: true
>
> domains: &domains
>   - domain: ads.example.com
>     type: deny
>     kind: exact
>     comment: Block ads domain
>     groups: [0]
>     enabled: true
>   - domain: ".*\\.tracking\\..*"
>     type: deny
>     kind: regex
>     comment: Block tracking subdomains
>     groups: [0]
>     enabled: true
>
> instances:
>   - name: home
>     base_url: http://192.168.1.100
>     password: "${PIHOLE_PASSWORD}"
>     config:
>       dns:
>         hosts: *hosts
>
>     lists: *lists
>     domains: *domains


Set your password:
```bash
$ export PIHOLE_PASSWORD="your-admin-password"
```

or use the `--dump` argument to grab an existing config. You'll need to at least have the instance defined with name, base_url and password in your local config in order to connect:

```bash
$ docker run --rm \
  -v $(pwd)/config:/config:ro \
  ghcr.io/dsgnr/confighole:latest -c /config/config.yaml -i homelab --dump
- name: homelab
  base_url: http://10.50.1.10
  config:
    dns:
      upstreams:
      - 127.0.0.1#5053
      CNAMEdeepInspect: true
      blockESNI: true
      EDNS0ECS: true
      ignoreLocalhost: false
      hosts:
      - ip: 10.50.1.1
         host: rtr0
[...]
```

Run commands:
```bash
# Dump current Pi-hole state
$ confighole -c config.yaml --dump

# Show what would change
$ confighole -c config.yaml --diff

# Sync with dry-run
$ confighole -c config.yaml --sync --dry-run

# Apply changes
$ confighole -c config.yaml --sync

# Run continuously (every 5 minutes by default)
$ confighole -c config.yaml --daemon
```

## Daemon Mode

Daemon mode is useful if you want your Pi-hole instances to drift as little as possible. It periodically compares the live state with your config and applies any differences.

```bash
# Default interval (5 minutes)
$ confighole -c config.yaml --daemon

# Custom interval
$ confighole -c config.yaml --daemon --interval 600

# Dry-run daemon (monitor only)
$ confighole -c config.yaml --daemon --dry-run

# Target a single instance
$ confighole -c config.yaml --daemon --instance home --interval 180
```

**Configuration Precedence:**
- CLI arguments take highest precedence
- Global config settings are used if CLI arguments are not specified
- Default values are used as fallback

**Example:** If your config sets `daemon_interval: 600` but you run with `--interval 300`, the CLI value wins.


### Environment Variables

Configure daemon mode using environment variables (useful for Docker):

| Variable | Description | Default |
|----------|-------------|---------|
| `CONFIGHOLE_DAEMON_MODE` | Enable daemon mode | `false` |
| `CONFIGHOLE_CONFIG_PATH` | Path to config file | Required |
| `CONFIGHOLE_DAEMON_INTERVAL` | Sync interval in seconds | `300` |
| `CONFIGHOLE_INSTANCE` | Target instance | All |
| `CONFIGHOLE_DRY_RUN` | Enable dry-run mode | `false` |
| `CONFIGHOLE_VERBOSE` | Log verbosity (0-2) | `1` |

## Configuration

### Global settings

Apply to all instances unless overridden:

- `timeout` - Tor request timeout in seconds
- `verify_ssl` - To enable or disable TLS verification
- `password` / `password_env` - For default authentication

**Daemon mode settings:**
- `daemon_mode` - Enable daemon mode by default (`true`/`false`)
- `daemon_interval` - Sync interval in seconds (default: `300`)
- `verbosity` - Log verbosity level (`0`=WARNING, `1`=INFO, `2`=DEBUG)
- `dry_run` - Enable dry-run mode by default (`true`/`false`)

### Instance settings

Per-instance configuration:

- `name` - Instance identifier
- `base_url` - Pi-hole web interface URL  
- `password` - Admin password (supports `${ENV_VAR}`)
- `update_gravity` - Automatically update gravity when lists change (`true`/`false`, default: `false`)
- `config` - Pi-hole configuration to manage
- `lists` - Pi-hole lists to manage
- `domains` - Pi-hole domains to manage (exact/regex, allow/deny)
- `groups` - Pi-hole groups to manage
- `clients` - Pi-hole clients to manage

### Domain configuration

Domains support both exact matches and regex patterns, for both allow and deny lists:

```yaml
domains:
  # Exact domain to block
  - domain: ads.example.com
    type: deny        # deny or allow
    kind: exact       # exact or regex
    comment: "Block ads"
    groups: [0]
    enabled: true

  # Regex pattern to allow
  - domain: ".*\\.trusted\\.com"
    type: allow
    kind: regex
    comment: "Allow trusted subdomains"
    groups: [0]
    enabled: true
```

### Group configuration

Groups allow you to organise clients and apply different filtering rules:

```yaml
groups:
  - name: family
    comment: "Family devices"
    enabled: true
  - name: iot
    comment: "IoT devices with strict filtering"
    enabled: true
```

### Client configuration

Clients can be identified by IP address, MAC address, hostname, subnet (CIDR), or interface:

```yaml
clients:
  - client: "192.168.1.50"
    comment: "John's laptop"
    groups: [0, 1]
  - client: "12:34:56:78:9A:BC"
    comment: "Smart TV"
    groups: [0]
  - client: "192.168.2.0/24"
    comment: "Guest network"
    groups: [2]
```

## Development

```bash
# Setup
$ poetry install

# Code quality
$ make lint        # ruff linting
$ make format      # ruff formatting  
$ make type-check  # mypy type checking

# All checks
$ make check
```

### Testing

ConfigHole includes a comprehensive test suite with both unit and integration tests:

```bash
# Run all tests
$ make test

# Run only unit tests (fast, no Pi-hole required)
$ make test-unit

# Run only integration tests (requires Pi-hole container)
$ make test-integration

# Run tests with coverage report
$ make test-coverage

# Start Pi-hole test container
$ make test-docker

# Stop Pi-hole test container  
$ make test-docker-down

# Stop and clean up Pi-hole test container (removes volumes)
$ make test-docker-clean
```

Integration tests spin up a real Pi-hole container from [pi-hole/docker-pi-hole](https://github.com/pi-hole/docker-pi-hole) to verify functionality. The test suite automatically manages the container lifecycle and waits for Pi-hole to be ready before running tests.

The test suite automatically cleans up the Pi-hole container after tests complete. If tests are interrupted, you can manually clean up with `make test-docker-clean`.

## Contributing

I'm thrilled that you’re interested in contributing to this project! Here’s how you can get involved:

### How to Contribute

1. **Submit Issues**:

   - If you encounter any bugs or have suggestions for improvements, please submit an issue on our [GitHub Issues](https://github.com/dsgnr/confighole/issues) page.
   - Provide as much detail as possible, including steps to reproduce and screenshots if applicable.

2. **Propose Features**:

   - Have a great idea for a new feature? Open a feature request issue in the same [GitHub Issues](https://github.com/dsgnr/confighole/issues) page.
   - Describe the feature in detail and explain how it will benefit the project.

3. **Submit Pull Requests**:
   - Fork the repository and create a new branch for your changes.
   - Make your modifications and test thoroughly.
   - Open a pull request against the `devel` branch of the original repository. Include a clear description of your changes and any relevant context.


## Author

- Website: https://danielhand.io
- Github: [@dsgnr](https://github.com/dsgnr)

## License

See the [LICENSE](LICENSE) file for more details on terms and conditions.