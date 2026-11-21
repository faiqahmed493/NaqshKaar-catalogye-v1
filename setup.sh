#!/usr/bin/env bash
# Naqshkaar Catalogue Studio - one-command setup for macOS and Linux.
#
#   ./setup.sh            first run: creates .env, builds, starts everything, runs the self-test
#   ./setup.sh            later runs: rebuilds and restarts with your existing .env
#
# Needs Docker Desktop (macOS) or Docker Engine with the Compose plugin (Linux).
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 1. Docker
say "Checking Docker"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Get Docker Desktop: https://www.docker.com/products/docker-desktop/"
docker compose version >/dev/null 2>&1 || die "'docker compose' is missing. Install the Docker Compose v2 plugin."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop, wait for 'Engine running', then rerun."
note "$(docker compose version)"

# ---------------------------------------------------------------- .env helpers
rand()   { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "${1:-32}" || true; }
getenv() { grep -E "^$1=" .env 2>/dev/null | head -n 1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'\$//" || true; }
setenv() {  # setenv KEY VALUE (portable replacement for sed -i)
  local tmp; tmp="$(mktemp)"
  K="$1" V="$2" awk 'BEGIN{k=ENVIRON["K"]; v=ENVIRON["V"]; done=0}
       index($0, k"=")==1 {print k"="v; done=1; next} {print}
       END{if(!done) print k"="v}' .env >"$tmp"
  mv "$tmp" .env
}
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
free_port() { local p="$1"; while port_busy "$p"; do p=$((p + 1)); done; echo "$p"; }

# ---------------------------------------------------------------- 2. .env
if [ ! -f .env ]; then
  say "Creating .env (your settings and secrets)"
  cp .env.example .env
  setenv POSTGRES_PASSWORD "$(rand 24)"
  setenv SECRET_KEY "$(rand 48)"
  note "Generated a database password and a secret key."

  read -rp "    Admin email for the studio: " email
  [ -n "$email" ] || die "An email is required."
  while :; do
    read -rsp "    Admin password (10+ characters): " pw; echo
    if [ "${#pw}" -lt 10 ]; then echo "    Too short."; continue; fi
    case "$pw" in *"'"*) echo "    Please avoid the ' character."; continue;; esac
    read -rsp "    Repeat the password: " pw2; echo
    [ "$pw" = "$pw2" ] && break || echo "    Passwords do not match."
  done
  setenv BOOTSTRAP_ADMIN_EMAIL "$email"
  setenv BOOTSTRAP_ADMIN_PASSWORD "'$pw'"

  for key in DB_PORT API_PORT WEB_PORT; do
    want="$(getenv "$key")"; got="$(free_port "$want")"
    if [ "$got" != "$want" ]; then setenv "$key" "$got"; note "Port $want is in use, so $key=$got."; fi
  done
else
  say "Using your existing .env"
fi
grep -Eq "^[^#]*CHANGE_ME" .env && die ".env still has CHANGE_ME values. Edit them, or delete .env and rerun this script."

API_PORT="$(getenv API_PORT)"; WEB_PORT="$(getenv WEB_PORT)"

# ---------------------------------------------------------------- 3. build and start
say "Building and starting the studio (the first build takes 5-15 minutes)"
docker compose up -d --build

say "Waiting for the API on http://localhost:${API_PORT}"
ok=""
for _ in $(seq 1 120); do
  if curl -fsS "http://localhost:${API_PORT}/api/health" >/dev/null 2>&1; then ok=1; break; fi
  printf '.'; sleep 5
done
echo
if [ -z "$ok" ]; then
  docker compose logs --tail=80 api
  die "The API did not start. The log above shows why; SETUP.md section 14 lists common fixes."
fi
note "API is healthy."

# ---------------------------------------------------------------- 4. mock 3D worker
if [ -z "$(getenv WORKER_API_KEY)" ]; then
  say "Creating an API key for the built-in 3D worker"
  key="$(docker compose exec -T api python -m app.cli create-api-key --name docker-mock-worker --scopes worker | tail -n 1 | tr -d '\r')"
  case "$key" in nqk_*) setenv WORKER_API_KEY "$key"; note "Saved to .env as WORKER_API_KEY.";;
                 *) die "Could not create the worker key: $key";; esac
fi
say "Starting the mock 3D worker (tests the pipeline without a GPU)"
docker compose --profile mock up -d --build generator-mock

# ---------------------------------------------------------------- 5. self-test
read -rp $'\n    Run the end-to-end self-test now? [Y/n] ' ans
if [ "${ans:-Y}" != "n" ] && [ "${ans:-Y}" != "N" ]; then
  sleep 5
  docker compose exec -T api python -m app.smoke || die "The self-test failed. Send the output above to get help."
fi

say "Done"
note "Web UI:   http://localhost:${WEB_PORT}    (sign in with $(getenv BOOTSTRAP_ADMIN_EMAIL))"
note "API docs: http://localhost:${API_PORT}/docs"
note "Stop:     docker compose --profile mock down      Start again: ./setup.sh"
