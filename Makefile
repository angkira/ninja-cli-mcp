.DEFAULT_GOAL := help

SHELL := /bin/sh

VERSION ?= 1.0.1
IMAGE ?= ninja-mcp:local-$(VERSION)
PROFILE ?= coder
COMPOSE_PROJECT_NAME ?= ninja-mcp
CONFIG_DIR ?= $(HOME)/.config/ninja-mcp/docker
CONFIG_ENV := $(CONFIG_DIR)/.env
COMPOSE_FILE ?= $(CURDIR)/docker-compose.yml
WRAPPER ?= $(CONFIG_DIR)/ninja-mcp-docker

.PHONY: help install install-native install-headless \
        docker-build docker-config docker-up docker-down docker-status \
        docker-logs docker-clean docker-run-agent analyze \
        test test-docker lint format-check typecheck check \
        version package release-check

help: ## Show categorized targets and examples
	@printf '%s\n' 'Ninja MCP 1.0.1 make targets'
	@printf '%s\n' '' 'Installation:'
	@printf '%s\n' '  make install          Run the interactive installer and choose Native/Docker in the TUI'
	@printf '%s\n' '  make install-native   Use make install; native has no separate non-interactive flow'
	@printf '%s\n' '  make install-headless Run the hidden Docker backend (NINJA_DOCKER_NONINTERACTIVE=1)'
	@printf '%s\n' '' 'Docker (requires a TUI-generated config):'
	@printf '%s\n' '  make docker-build PROFILE=coder IMAGE=ninja-mcp:local-1.0.1'
	@printf '%s\n' '  make docker-config PROFILE=researcher'
	@printf '%s\n' '  make docker-up PROFILE=coder COMPOSE_PROJECT_NAME=ninja-mcp'
	@printf '%s\n' '  make docker-status | docker-logs | docker-down'
	@printf '%s\n' '  make docker-clean     Explicitly remove containers, networks, and volumes'
	@printf '%s\n' '' 'Quality and release:'
	@printf '%s\n' '  make test             Run the full pytest suite through uv'
	@printf '%s\n' '  make check            Run lint, format-check, typecheck, and tests'
	@printf '%s\n' '  make version          Print the package version'
	@printf '%s\n' '  make package          Build Python distributions with uv'
	@printf '%s\n' '  make release-check    Run checks and build, without publishing'

install: ## Run the normal interactive Native/Docker TUI installer
	./install.sh

install-native: ## Document the native-only installation flow
	@printf '%s\n' 'No separate native-only automation is supported. Run: make install'
	@printf '%s\n' 'Then choose Native installation in the first TUI question.'

install-headless: ## Run the hidden, internal non-interactive Docker installer backend
	NINJA_DOCKER_NONINTERACTIVE=1 ./install.sh

$(CONFIG_ENV):
	@printf '%s\n' 'Docker config is missing: run make install and choose Docker in the TUI first.' >&2
	@false

docker-build: $(CONFIG_ENV) ## Build the selected Docker profile image
	NINJA_DOCKER_IMAGE="$(IMAGE)" docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" build

docker-config: $(CONFIG_ENV) ## Print resolved Compose configuration without starting services
	NINJA_DOCKER_IMAGE="$(IMAGE)" docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" config

docker-up: $(CONFIG_ENV) ## Start the selected profile in the background
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" up -d

docker-down: $(CONFIG_ENV) ## Stop the selected Compose project
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" down

docker-status: $(CONFIG_ENV) ## Show selected profile container status
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" ps

docker-logs: $(CONFIG_ENV) ## Follow selected profile logs
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" logs -f

docker-clean: $(CONFIG_ENV) ## Explicitly remove the project, orphan containers, and named volumes
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile "$(PROFILE)" -f "$(COMPOSE_FILE)" down --volumes --remove-orphans

docker-run-agent: $(CONFIG_ENV) ## Run one agent command without exposing credentials
	docker compose --project-name "$(COMPOSE_PROJECT_NAME)" --env-file "$(CONFIG_ENV)" --profile agent -f "$(COMPOSE_FILE)" run --rm agent

analyze: docker-run-agent ## Alias for the one-shot agent wrapper

test: ## Run tests using the repository's uv workflow
	uv run pytest tests/ -v --tb=short -x

test-docker: docker-config ## Validate the selected Docker Compose configuration

lint: ## Run CI-aligned Ruff linting
	uv run ruff check src/ tests/

format-check: ## Check CI-aligned Ruff formatting
	uv run ruff format --check src/

typecheck: ## Run CI-aligned mypy type checking
	uv run mypy src/ --ignore-missing-imports

check: lint format-check typecheck test ## Run all local quality checks

version: ## Print the project version
	uv run ninja-mcp version

package: ## Build Python distributions without publishing
	uv build

release-check: check package ## Validate and build a release without publishing
