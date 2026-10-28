"""Decode Valve replays by file signature, not the legacy .dem.bz2 suffix."""
import bz2
import shutil

DEMO_HEADERS = (b"PBDEMS2\x00", b"HL2DEMO\x00")
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class ReplayDecodeError(RuntimeError):
    pass


def _copy_zstandard(source, output):
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError("Zstandard replay support requires dependencies: run python -m pip install -r requirements.txt in the API directory.") from exc
    decoder = zstandard.ZstdDecompressor().decompressobj()
    saw_frame = False
    try:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                if not saw_frame or not decoder.eof:
                    raise ReplayDecodeError("Zstandard replay is truncated; download the archive again.")
                return
            if decoder.eof:
                decoder = zstandard.ZstdDecompressor().decompressobj()
            while chunk:
                output.write(decoder.decompress(chunk))
                if decoder.eof:
                    saw_frame = True
                    chunk = decoder.unused_data
                    if chunk:
                        decoder = zstandard.ZstdDecompressor().decompressobj()
                else:
                    chunk = b""
    except zstandard.ZstdError as exc:
        raise ReplayDecodeError("Zstandard replay is corrupt; download the archive again.") from exc


def unpack_replay(archive, target):
    """Atomically produce a validated .dem; retain the original archive on error."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with archive.open("rb") as source, tmp.open("wb") as output:
            signature = source.read(8)
            source.seek(0)
            if signature.startswith(ZSTD_MAGIC):
                _copy_zstandard(source, output)
            elif signature.startswith(b"BZh"):
                try:
                    with bz2.BZ2File(source, "rb") as decoded:
                        shutil.copyfileobj(decoded, output, 64 * 1024)
                except (OSError, EOFError) as exc:
                    raise ReplayDecodeError("BZip2 replay is corrupt or truncated; download the archive again.") from exc
            elif signature in DEMO_HEADERS:
                shutil.copyfileobj(source, output, 64 * 1024)
            else:
                raise ReplayDecodeError(f"Unsupported replay contents (header {signature.hex()}). Expected BZip2, Zstandard or a Dota demo; the server may have returned an error page.")
        with tmp.open("rb") as decoded:
            if decoded.read(8) not in DEMO_HEADERS:
                raise ReplayDecodeError("Decoded file is not a Dota replay. The downloaded response may be an error page.")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
