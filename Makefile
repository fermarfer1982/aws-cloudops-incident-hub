.PHONY: up down logs test lint synth validate seed simulate-async clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

test:
	python -m pytest -q

lint:
	ruff check backend tests infrastructure scripts

synth:
	cd infrastructure && cdk synth

validate: lint test synth
	python scripts/check_zero_cost.py infrastructure/cdk.out/CloudOpsIncidentHubStack.template.json

seed:
	bash scripts/seed_demo.sh

simulate-async:
	bash scripts/simulate_sqs_event.sh

clean:
	docker compose down -v
	rm -rf infrastructure/cdk.out .pytest_cache .ruff_cache
