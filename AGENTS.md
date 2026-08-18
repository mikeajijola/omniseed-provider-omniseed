# Working on the OmniSeed Provider

- Provider organisation and canonical ID: OmniSeed / `omniseed`.
- Engine operations, governance evaluation, capability inspection, and reconciliation observation are products/implementations beneath OmniSeed, not separate Providers.
- This package supports `skills`, `policies`, and `observations`; it never directly realises business Capabilities.
- The public `omniseed-ecosystem` repository must never become a runtime dependency.
- Git remains canonical desired state. Projection and Activity are Engine-owned runtime state.
- Apply binds approved primitive resources; observation must inspect the deployed Engine projection and return evidence.
- Never print or return operation credentials.
- Run `npm test` before proposing a change.
