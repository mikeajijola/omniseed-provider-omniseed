# OmniSeed Provider

This package is the Provider boundary for implementations supplied by the
OmniSeed organisation itself. It exposes Engine-native implementations for the
canonical `skills`, `policies`, and `observations` primitive families.

It does **not** make the public `omniseed-ecosystem` governance repository a
runtime dependency. The runtime talks only to an ordinary deployed OmniSeed
operation/projection endpoint and returns evidence about the bound company.

OmniSeed remains a Provider beneath primitive realisations. It does not claim
to realise business Capabilities directly.

```sh
OMNISEED_PROVIDER_OPERATION_TOKEN=... python3 provider/omniseed_provider.py
npm test
```

The token is optional for a read-only endpoint and is never returned in
evidence.
