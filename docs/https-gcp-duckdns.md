# HTTPS on Google Cloud with DuckDNS

This guide is for the current VM deployment that serves StarBegonia on port
5173 using `docker-compose.yml`. Local development and remote deployment have
separate scripts; local deployment does not load the HTTPS overlay and remains
at `http://localhost:5173`.

For local development, run this from the project root:

```bash
./scripts/deploy-local.sh
```

It creates `.env` from `.env.example` only if local `.env` is missing, then
builds and starts the regular local stack.

## 1. Point DuckDNS at the VM

Check that `1cchome1.duckdns.org` resolves to the VM's external IP. If the VM
uses an ephemeral IP, configure a DuckDNS updater or assign the VM a static
external IP in Google Cloud.

## 2. Allow public HTTP and HTTPS in Google Cloud

Create an ingress VPC firewall rule for TCP ports 80 and 443, source range
`0.0.0.0/0`, targeting the network tag `starbegonia-web`. Add this tag to the
VM. Or run the following on a machine with `gcloud` configured, replacing the
instance name and zone:

```bash
gcloud compute instances add-tags INSTANCE_NAME --zone ZONE --tags starbegonia-web
gcloud compute firewall-rules create starbegonia-web-https \
  --network default --direction INGRESS --action ALLOW \
  --rules tcp:80,tcp:443 --source-ranges 0.0.0.0/0 \
  --target-tags starbegonia-web
```

If `ufw` is enabled on the VM, allow the same ports:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

## 3. Set the public application origin

On the VM, edit `.env`:

```env
APP_PUBLIC_URL=https://1cchome1.duckdns.org
CORS_ORIGINS=https://1cchome1.duckdns.org
```

## 4. Deploy the HTTPS stack

Install `rsync` on the VM if needed (`sudo apt install -y rsync`) and confirm
SSH access from your development machine. Run this from the local project root,
replacing `SSH_USER` with your VM login:

```bash
./scripts/deploy-gcp.sh SSH_USER@1cchome1.duckdns.org
```

The script syncs project files and removes stale code files from the remote
project directory. It excludes `.env` and secret files, then builds and starts
the HTTPS stack remotely. Use a dedicated project directory. The script
requires an existing `~/StarBegonia/.env` and checks its HTTPS origin before
deploying. Caddy obtains and renews the certificate automatically; its data is
stored in the `caddy_data` volume. To inspect Caddy logs, run:

```bash
ssh SSH_USER@1cchome1.duckdns.org 'cd StarBegonia && docker compose -f docker-compose.yml -f docker-compose.https.yml logs --tail=100 caddy'
```

Once `https://1cchome1.duckdns.org/account` loads, remove the old public GCP
ingress rule for TCP port 5173. Keep the 5173 mapping in Compose if desired;
without a GCP firewall rule it is not reachable from the internet.

This overlay is for the stack that currently uses port 5173. The separate
`docker-compose.free.yml` already publishes port 80 and needs a different
override to avoid a port conflict.
