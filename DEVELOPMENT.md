# Local API startup

Run `python server.py` (Python 3.10+). The default API port is 8080; override it with `PORT`.

- `GET /health`: HTTP 200 JSON with `service: OpenDoter API` and `status: ok`.
- `GET /`: the same service identity plus instructions for opening the separate PHP site.
- Unknown paths still return HTTP 404 JSON. Existing API endpoints are unchanged.

These endpoints check HTTP-server liveness only, not OpenDota connectivity or parser readiness. They do not download data or invoke the parser.

The API is not the PHP frontend. Start `run-all.bat` in the OpenDoter site repository and use the exact site URL printed by its launcher. The launcher can select another port if Windows reserves port 8000.

Regression tests (standard library only, no external API requests):

```bash
python -m unittest discover -s tests -v
```
