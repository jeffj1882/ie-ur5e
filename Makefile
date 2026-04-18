.PHONY: install lint test sim-up sim-down sim-logs sim-shell sim-teach connect-check api-dev fmt clean

UV ?= uv
ARCH := $(shell uname -m)

# Stamp used by sim-up to know when the container is healthy.
URSIM_CONTAINER := ursim

install: ## Install runtime + dev deps into .venv via uv
	$(UV) sync

fmt: ## Format with ruff
	$(UV) run ruff format src tests

lint: ## Ruff check + format check
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

test: ## Run pytest (integration tests auto-skip without ROBOT_IP)
	$(UV) run pytest -q

connect-check: ## Verify package imports and config loads
	$(UV) run ie-ur5e-check

api-dev: ## FastAPI with reload on :8080
	$(UV) run uvicorn ie_ur5e.api:app --host 127.0.0.1 --port 8080 --reload

sim-up: ## Start URSim and block until it responds on :29999
ifeq ($(ARCH),arm64)
	@echo "⚠️  Apple Silicon detected — URSim runs under linux/amd64 emulation (slow but functional)."
endif
	docker compose up -d ursim
	$(UV) run python scripts/wait_for_ursim.py

sim-down:
	docker compose down -v

sim-logs:
	docker compose logs -f ursim

sim-shell:
	docker compose exec $(URSIM_CONTAINER) bash

sim-teach: ## Open the noVNC teach pendant
	@open http://localhost:6080/vnc.html?autoconnect=1 2>/dev/null || \
		echo "Open http://localhost:6080 in your browser"

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
