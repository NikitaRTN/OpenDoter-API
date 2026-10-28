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

On Windows the API uses an exclusive listening socket. A second API instance fails with a clear startup error instead of silently sharing the port with an older instance. Restart the previous OpenDoter API process before running the updated version.

## Replay compression

Before parsing replays, install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Valve replay URLs may end with `.dem.bz2` even when their contents use Zstandard. The API detects BZip2, Zstandard and uncompressed demos from their signatures, not filenames. Decoding is incremental and the `.dem` is replaced atomically only after successful decompression and demo-header validation. Cached archives are reused; a format mismatch does not require downloading the replay again.

A truncated archive, unknown response format or decoded non-demo produces a specific error and never replaces a previously valid `.dem`. Original archives remain available for diagnostics. Restart the API after updating its code or dependencies.
