---
name: Python security review
slug: python
language: python
---

Review Python code for deserialization (`pickle`, `yaml.load`), SSTI, SQL injection,
path traversal, unsafe `subprocess`/`os.system`, and SSRF in HTTP clients.
Prefer authentic high-impact issues over config/docs noise.
