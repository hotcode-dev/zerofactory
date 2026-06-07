# Hermes Config Layout

This folder uses a shared `.env` link flow and `yq` for YAML config merging.

## Env Link Flow

- `hermes/profiles/common/.env` is the source file (regular file).
- `hermes/profiles/<profile>/.env -> ../common/.env`

Notes:

- Root env and config files are not part of this profile link flow.

## YAML Merge With yq

Use `yq` to build effective config files from:

- Base: `hermes/profiles/common/config.yaml`
- Overlay: `hermes/profiles/<profile>/config.custom.yaml`
- Output (runtime): `hermes/profiles/<profile>/config.yaml`

Example merge command:

```bash
yq eval-all '. as $item ireduce ({}; . * $item )' \
	hermes/profiles/common/config.yaml \
	hermes/profiles/builder/config.custom.yaml > hermes/profiles/builder/config.yaml
```

Script helper:

```bash
./hermes/bin/merge-config.sh
```

To link common skills to all profiles:

```bash
./hermes/bin/link-skills.sh
```

For each profile other than `common`, keep custom overrides in `config.custom.yaml`.
Regenerate `config.yaml` when custom or common settings change.

This setup avoids YAML merge keys inside config files and keeps merge behavior explicit.
