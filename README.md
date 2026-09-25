# IRIS Vector DB Management Portal

Administration portal for discovering, inspecting, querying and managing vector resources in InterSystems IRIS 2026.2 Community Edition.

The application runs as a WSGI callable inside IRIS Embedded Python. There is no Flask, Waitress or separate application server. Administrative context comes from the pinned SysAdmin API v2 contract; vector metadata and operations use native IRIS SQL and dictionary metadata.

## First operational release

- bounded inventory of `VECTOR` and `EMBEDDING` columns;
- explicit `Unknown` provenance for unbound vectors;
- keyset-paged row inspection without vectors in the initial response;
- separately requested, bounded vector previews;
- parameterized vector and managed-text similarity search;
- actual `EXPLAIN` diagnosis: `HNSW used`, `Full scan` or `Undetermined`;
- namespace, database, global mapping and storage evidence;
- sanitized embedding configuration views;
- guarded HNSW creation with eligibility checks, exact target confirmation, a short-lived single-use token, catalog revalidation, asynchronous execution and auditing;
- creation of a new `VECTOR(DOUBLE, n)` column in a selected table, sourced by a validated two-column `SELECT` and populated by the same IRIS task using either an embedding configuration or trusted Embedded Python code;
- key-based updates that match the first source result column to the selected relationship column in the destination table;
- repeatable execution policies (`ALL`, `CHANGED`, `MISSING`) with source/model signatures, per-target leases and created/updated/skipped/missing counters;
- `data.Document` automatically populated with Faker during builds with fixtures enabled; no seeder screen or HTTP endpoint;
- Python editor syntax validation with line and column feedback plus non-persistent sample testing;
- server-side limits for pages, top-K, dimensions, response size, execution time and concurrent searches.

Configuration mutation, index rebuild/drop, general joins/expressions in source SQL and multi-instance writes remain disabled until their later acceptance gates are implemented.

## Run

```sh
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:52773/vector-admin/` and authenticate with an IRIS account holding `VectorAdmin_Read`. The image creates the roles and authenticated WSGI application but deliberately does not bake in a human password.

The default build includes small offline fixtures. Set `WITH_FIXTURES=0` in `.env` to omit SentenceTransformers and fixture data.

## Roles

- `VectorAdminReader`: inventory and portal read access.
- `VectorAdminMaintainer`: guarded vector maintenance plus read access.
- `VectorAdminAdministrator`: portal administration plus read access.

Portal checks supplement IRIS SQL object permissions and SysAdmin privileges. Grant table `SELECT`/`ALTER`, `%Admin_Manage`, `%USE_EMBEDDING`, and database/catalog access according to the operator's actual duties.

## Contract and evidence

The pinned SysAdmin revision is recorded in `vendor/sysadmin-revision.txt`. `docs/sysadmin-api-map.md` is generated from that OpenAPI document, and `vendor/sysadmin-allowlist.json` constrains the client to verified read operations.

The bounded scale fixture is capped at 500,000 records for Community Edition and is not created by the normal image build.

## Verification

```sh
python -m unittest discover -s tests -v
node --check vector_admin/static/app.js
docker compose config --quiet
```

The integration scripts under `tools/` validate the installed 2026.2 catalog representation, managed embeddings, HNSW metadata and plans.
