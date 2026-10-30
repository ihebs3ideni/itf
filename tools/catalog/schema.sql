-- ITF pack catalog. Built by tools/catalog/build_catalog.py from the packs' @provides/@delivers
-- decorators. Read it with `SELECT name, sql FROM sqlite_master`: the comments below are kept.
-- Tokens: capabilities are itf.capabilities.<area>.<name>, states are itf.states.<area>.<name>.
-- Providers and actions are keyed by (name, module): one name can exist in real and sim variants.

CREATE TABLE packs (
  -- one row per packs/itf_pack_* directory
  name TEXT PRIMARY KEY,        -- e.g. itf_pack_shell
  doc TEXT,                     -- package docstring, one line
  readme TEXT,                  -- README.md: object API, config, examples, caveats
  requirements TEXT             -- comma-separated requirement*.txt files shipped with the pack
);

CREATE TABLE entrypoints (
  -- modules a recipe lists in pytest_plugins to load a pack (or one variant of it)
  name TEXT PRIMARY KEY,        -- e.g. itf_pack_shell.plugin, itf_pack_container.sim.plugin
  pack TEXT REFERENCES packs(name),
  doc TEXT
);

CREATE TABLE entrypoint_modules (
  -- every module an entrypoint loads, itself included (follows pytest_plugins transitively)
  entrypoint TEXT REFERENCES entrypoints(name),
  module TEXT
);

CREATE TABLE capabilities (
  -- contract tokens: something a test or another provider can hold
  token TEXT PRIMARY KEY,
  area TEXT                     -- e.g. exec, net, power, observe
);

CREATE TABLE states (
  -- state tokens: conditions actions make true; recipes ask for them as goals
  token TEXT PRIMARY KEY,
  area TEXT
);

CREATE TABLE providers (
  -- implementations of a capability; a recipe node picks one with `using: <name>`
  name TEXT,                    -- e.g. ssh.exec
  module TEXT,                  -- defining module; join entrypoint_modules to find what loads it
  contract TEXT REFERENCES capabilities(token),
  pack TEXT REFERENCES packs(name),
  variant TEXT,                 -- real | sim | generic | legacy | multicast | host | shared
  doc TEXT,
  PRIMARY KEY (name, module)
);

CREATE TABLE provider_members (
  -- what a test may call on the node: only these members are part of the contract
  provider TEXT, module TEXT,
  member TEXT,
  signature TEXT,               -- e.g. "(cmd: str, timeout: float = 30.0) -> tuple[int, str]"; "(property)"; ": str"
  doc TEXT                      -- first paragraph of the member docstring
);

CREATE TABLE provider_needs (
  -- slots a provider fills from other nodes in its scope (auto-filled when exactly one matches)
  provider TEXT, module TEXT,
  slot TEXT,                    -- name to use in `bind: {slot: node}` when several nodes match
  contract TEXT,
  members TEXT                  -- comma-separated members it uses from that node
);

CREATE TABLE provider_config (
  -- keys accepted under a node's `config:`; unknown keys fail resolution
  provider TEXT, module TEXT,
  field TEXT,
  type TEXT,
  required INTEGER,             -- 1: must be set in the recipe
  sensitive INTEGER,            -- 1: secret-like; point at a file, never inline a secret
  default_json TEXT             -- JSON default when optional and not sensitive
);

CREATE TABLE actions (
  -- steps that make a state true; OCTO orders them from requires/invalidates
  name TEXT,                    -- e.g. power.enable; pin one with init.states: [{token, using: name}]
  module TEXT,
  state TEXT REFERENCES states(token),
  pack TEXT REFERENCES packs(name),
  variant TEXT,
  probe INTEGER,                -- 1: skipped when a probe sees the state already true
  doc TEXT,
  PRIMARY KEY (name, module)
);

CREATE TABLE action_relations (
  -- extra states an action delivers (also), needs first (requires) or destroys (invalidates)
  action TEXT, module TEXT,
  kind TEXT,                    -- also | requires | invalidates
  ref TEXT,                     -- as declared; "scope:token" or ":token" (root) when scoped
  scope TEXT,                   -- scope part of ref, NULL when unscoped (same scope as the action)
  state TEXT                    -- token part of ref
);

CREATE TABLE action_uses (
  -- capability slots an action operates on (nodes of its scope)
  action TEXT, module TEXT,
  slot TEXT,
  contract TEXT,
  members TEXT
);

CREATE TABLE load_errors (
  -- entrypoints that failed to import while building (e.g. missing optional dependency)
  entrypoint TEXT,
  error TEXT
);

CREATE TABLE meta (
  key TEXT PRIMARY KEY,         -- source_hash: fingerprint of the packs this was built from; counts
  value TEXT
);

-- Full-text index over every row kind (capability | state | provider | member | action | pack);
-- id is the token or name (member: provider.member). Query:
--   SELECT kind, id, title FROM search WHERE search MATCH 'ping OR boot' ORDER BY rank LIMIT 20
CREATE VIRTUAL TABLE search USING fts5(kind, id, title, body, tokenize = 'porter unicode61');

CREATE VIEW v_capability_providers AS
  -- who provides each capability, and which entrypoints load each provider
  SELECT p.contract AS capability, p.name AS provider, p.pack, p.variant,
         group_concat(em.entrypoint, ', ') AS entrypoints
  FROM providers p LEFT JOIN entrypoint_modules em ON em.module = p.module
  GROUP BY p.contract, p.name, p.module;

CREATE VIEW v_state_deliverers AS
  -- which actions make each state true, what they need first and what they destroy
  SELECT a.state, a.name AS action, a.pack, a.variant, a.probe,
         (SELECT group_concat(r.ref, ', ') FROM action_relations r
          WHERE r.action = a.name AND r.module = a.module AND r.kind = 'requires') AS requires,
         (SELECT group_concat(r.ref, ', ') FROM action_relations r
          WHERE r.action = a.name AND r.module = a.module AND r.kind = 'invalidates') AS invalidates,
         (SELECT group_concat(u.slot || '=' || u.contract, ', ') FROM action_uses u
          WHERE u.action = a.name AND u.module = a.module) AS uses,
         (SELECT group_concat(em.entrypoint, ', ') FROM entrypoint_modules em
          WHERE em.module = a.module) AS entrypoints
  FROM actions a;

CREATE VIEW v_provider_api AS
  -- the members a test may call, with signature, per provider
  SELECT p.contract AS capability, p.name AS provider, p.variant, m.member, m.signature, m.doc
  FROM providers p JOIN provider_members m ON m.provider = p.name AND m.module = p.module;

CREATE VIEW v_recipe_node AS
  -- everything needed to write one recipe node: entrypoints, slots and config keys
  SELECT p.name AS provider, p.contract,
         (SELECT group_concat(em.entrypoint, ', ') FROM entrypoint_modules em WHERE em.module = p.module) AS entrypoints,
         (SELECT group_concat(n.slot || '=' || n.contract, ', ') FROM provider_needs n
          WHERE n.provider = p.name AND n.module = p.module) AS needs,
         (SELECT group_concat(c.field || ':' || c.type || CASE WHEN c.required THEN '!' ELSE '' END, ', ')
          FROM provider_config c WHERE c.provider = p.name AND c.module = p.module) AS config
  FROM providers p;
