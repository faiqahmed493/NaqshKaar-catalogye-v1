# Convenience commands (Linux/macOS). On Windows run the docker compose lines directly.
.PHONY: up down logs ps admin key test seed check psql mock

up:            ## build and start database, API, worker and web UI
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f api worker
ps:
	docker compose ps
admin:         ## make EMAIL=you@x.com NAME="You" admin
	docker compose exec api python -m app.cli create-user --email "$(EMAIL)" --name "$(NAME)" --role admin
key:           ## make key NAME=lab-gpu SCOPES=worker
	docker compose exec api python -m app.cli create-api-key --name "$(NAME)" --scopes "$(SCOPES)"
seed:
	docker compose exec api python -m app.cli seed
check:
	docker compose exec api python -m app.cli check
psql:
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
mock:          ## start the CPU mock 3D worker (needs WORKER_API_KEY in .env)
	docker compose --profile mock up -d --build generator-mock
test:
	cd backend && python -m pytest -q
