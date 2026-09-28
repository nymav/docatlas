# Security model

DocAtlas is intended for one trusted workspace on localhost or behind an authenticated
TLS reverse proxy. A shared workspace API key grants access to all its documents and
write operations. It does not provide user-level ACLs or tenant isolation.

Implemented controls: constant-time key comparison, no secrets in browser configuration,
same-origin writes, content-size limits, fixed file types, no arbitrary URL fetching,
parameterized SQL, bounded provider output, no agent tools, exact quote/source checks,
HTML rendered as text, restrictive Content Security Policy, and process-local limits.
Uploads require Content-Length. PDFs must be unencrypted and at most 300 pages.

Threat boundaries: retrieved documents are untrusted content; the model never receives
tools or permission to execute instructions from them. However prompt injection can
still influence answer wording, and quote matching is not an entailment proof. Always
inspect evidence for important decisions. Treat generated answers as untrusted output.

Upload parsers execute in-process. Byte/page/text limits do not fully prevent malicious
PDF decompression or parser-resource attacks; accept documents from trusted workspace
members, run inside memory-limited containers, and use a sandboxed ingestion worker
before accepting arbitrary internet uploads. Localhost binding alone is not an
authentication boundary on a shared machine; set a workspace API key there too.

Source content remains in SQLite; generation sends selected passages to the configured
provider. Feedback notes are stored locally. Request logs avoid document bodies and
provider credentials. Do not commit `.env`, database files, model caches or user uploads.
Rotate the workspace key by updating the environment and restarting the server.

Report security issues privately to the repository owner rather than uploading private
documents, credentials or exploit results in a public issue.
