.PHONY: dev compose-up compose-build test lint build
dev:
	docker compose up --build
compose-up:
	docker compose up --build -d
compose-build:
	docker compose build
test:
	cd upcode-forge-service && python -m pytest
	cd upcode-forge && npm test
lint:
	cd upcode-forge-service && ruff check .
	cd upcode-forge && npm run lint && npm run typecheck
build:
	cd upcode-forge && npm run build
