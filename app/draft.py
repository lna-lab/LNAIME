"""原稿の蔵 — drafts live here, on SAZANAMI, and nowhere else.

LNAIME's reason for being is 原稿が外に出ない (the manuscript never leaves). This is where
the manuscript is *kept*: a tiny, dependency-free draft store so a roaming client (ANDON-Code
on a MacBook, over Tailscale) can compose into a draft that persists on this box and is never
written to the laptop's disk. The client holds a window; the text lives here.

Design, matching the LNA-OS house creed (robustness #1):
- **Local only.** Plain files under a drafts directory; this module never touches the network.
- **Atomic + durable.** tmp-in-same-dir → fsync → os.replace → fsync(dir): a crash mid-save
  never corrupts an existing draft (you get the whole old one or the whole new one).
- **Fail-closed ids.** A draft id is client-supplied for autosave continuity; it is strictly
  validated (``[A-Za-z0-9_-]+``) so it can never escape the drafts directory (no ``../``).
- **Stdlib only.** No fastapi/pydantic in here — the store is a pure, unit-testable object;
  the HTTP shell (server.py) is the only async/web part.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

# A draft id is part of a filesystem path, so it is validated to a safe alphabet — this is the
# wall against path traversal (a client-supplied "../../etc/x" can never be a draft id).
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _now_ms() -> int:
    return int(time.time() * 1000)


class DraftError(Exception):
    """A draft operation failed loudly (bad id, missing draft) — never a silent wrong file."""


class DraftStore:
    """A directory of drafts. One JSON file per draft: ``{id, title, body, created_ms, updated_ms}``."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- ids -----------------------------------------------------------------------------

    @staticmethod
    def _validate_id(draft_id: str) -> str:
        if not isinstance(draft_id, str) or not _ID_RE.match(draft_id):
            raise DraftError(
                f"invalid draft id {draft_id!r} (allowed: letters, digits, '-', '_', 1–64 chars)"
            )
        return draft_id

    def _new_id(self) -> str:
        # Time-ordered + random so ids sort roughly by creation and never collide.
        for _ in range(8):
            candidate = f"d{_now_ms():013d}-{secrets.token_hex(3)}"
            if not self._path(candidate).exists():
                return candidate
        raise DraftError("could not allocate a unique draft id")  # practically unreachable

    def _path(self, draft_id: str) -> Path:
        return self.dir / f"{draft_id}.json"

    # ---- the four operations -------------------------------------------------------------

    def save(self, body: str, draft_id: str | None = None, title: str | None = None) -> dict:
        """Upsert a draft. No id ⇒ a new one is minted and returned; an existing id keeps its
        ``created_ms`` and bumps ``updated_ms``. The write is atomic and fsync-durable."""
        if draft_id is None or draft_id == "":
            draft_id = self._new_id()
            created_ms = _now_ms()
        else:
            self._validate_id(draft_id)
            existing = self._read_raw(draft_id)
            created_ms = existing["created_ms"] if existing else _now_ms()

        record = {
            "id": draft_id,
            "title": (title or "").strip(),
            "body": body if isinstance(body, str) else "",
            "created_ms": created_ms,
            "updated_ms": _now_ms(),
        }
        self._atomic_write(draft_id, record)
        return self._meta(record)

    def load(self, draft_id: str) -> dict:
        """The full draft (incl. ``body``). Raises [DraftError] if the id is bad or absent."""
        self._validate_id(draft_id)
        record = self._read_raw(draft_id)
        if record is None:
            raise DraftError(f"no draft {draft_id!r}")
        return record

    def list(self) -> list[dict]:
        """Every draft's metadata (no body), newest first."""
        out: list[dict] = []
        for p in self.dir.glob("*.json"):
            try:
                record = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # a corrupt/partial file is skipped from the index, never crashes the list
            out.append(self._meta(record))
        out.sort(key=lambda m: m.get("updated_ms", 0), reverse=True)
        return out

    def delete(self, draft_id: str) -> bool:
        """Remove a draft. Returns whether it existed."""
        self._validate_id(draft_id)
        path = self._path(draft_id)
        try:
            path.unlink()
            _fsync_dir(self.dir)
            return True
        except FileNotFoundError:
            return False

    # ---- internals -----------------------------------------------------------------------

    def _read_raw(self, draft_id: str) -> dict | None:
        path = self._path(draft_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as e:
            raise DraftError(f"draft {draft_id!r} is unreadable: {e}") from e

    def _atomic_write(self, draft_id: str, record: dict) -> None:
        data = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
        # tmp in the SAME dir so os.replace is atomic (same filesystem), then fsync the dir so
        # the rename itself is durable — the manuscript survives a crash an instant later.
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=f".{draft_id}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path(draft_id))
            _fsync_dir(self.dir)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _meta(record: dict) -> dict:
        return {
            "id": record.get("id", ""),
            "title": record.get("title", ""),
            "updated_ms": record.get("updated_ms", 0),
            "created_ms": record.get("created_ms", 0),
            "chars": len(record.get("body", "")),
        }


def _fsync_dir(directory: Path) -> None:
    """fsync a directory so a create/rename/unlink of its entries is durable (POSIX)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


# A self-contained test that runs WITHOUT pytest (the box's .venv has no test deps; the store
# is pure stdlib): `python3 app/draft.py` exercises save/load/list/delete, atomicity-by-replace,
# created_ms preservation, and the path-traversal wall.
if __name__ == "__main__":
    import shutil

    tmpdir = tempfile.mkdtemp(prefix="lnaime-draft-test-")
    try:
        store = DraftStore(tmpdir)

        # save (new id minted) → load round-trips the body
        m = store.save("雪乃の部屋に灯りをともす", title="夜の章")
        did = m["id"]
        assert m["title"] == "夜の章" and m["chars"] == 12, m
        full = store.load(did)
        assert full["body"] == "雪乃の部屋に灯りをともす", full
        created = full["created_ms"]

        # update keeps created_ms, bumps updated_ms
        time.sleep(0.002)
        m2 = store.save("雪乃の部屋に灯りをともす。藤の香り。", draft_id=did, title="夜の章")
        assert store.load(did)["created_ms"] == created, "created_ms must be preserved"
        assert m2["updated_ms"] >= full["updated_ms"], "updated_ms must advance"

        # a second draft, then list is newest-first
        store.save("別の原稿", title="昼の章")
        names = [d["title"] for d in store.list()]
        assert set(names) == {"夜の章", "昼の章"} and len(names) == 2, names

        # an empty / None id is the "mint me a new draft" signal (first autosave), not a bad id
        minted = store.save("first autosave", draft_id="")
        assert minted["id"] and minted["id"] != did, minted

        # NON-EMPTY malformed ids are refused (the path-traversal wall)
        for bad in ["../escape", "a/b", "..", "x" * 65, "a b", "draft.json", "."]:
            try:
                store.save("x", draft_id=bad)
                raise AssertionError(f"bad id accepted: {bad!r}")
            except DraftError:
                pass

        # load of a missing draft is a loud DraftError, never a silent empty
        try:
            store.load("d0000000000000-deadbe")
            raise AssertionError("missing load should raise")
        except DraftError:
            pass

        # delete
        assert store.delete(did) is True
        assert store.delete(did) is False
        print("draft.py self-test: OK (save/load/list/delete, atomic, created_ms, traversal-wall)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
