"""ReproLens as a web product: drop a paper, watch it being read, get the result.

    uv run python -m app.server          # http://localhost:8765

A thin layer over ``audit.py``. It runs the audit as a subprocess, relays the
progress events the audit emits (``--progress``) to the browser as they
happen, and serves the result through ``reprolens.reporting.view`` -- which is
the one place presentation rules live, so this page and the CLI report cannot
disagree about an audit.

Nothing is kept. Each upload goes into its own empty working directory and is
passed to the audit by path; the directory is deleted when the job is deleted,
when it is evicted, or when the server stops. Nothing uploaded, and nothing in
any repository the paper points at, is ever executed. This file never reads
``benchmark/``; a test enforces it.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from reprolens.extraction import vlm
from reprolens.reporting import view

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
AUDIT = ROOT / "audit.py"

VLM_BACKEND = os.environ.get("REPROLENS_VLM", "ollama")
# Extra audit flags, for running the server against a reduced pipeline (tests
# pass --no-repo --no-resolve --no-vlm here so a request finishes in seconds).
EXTRA_ARGS = os.environ.get("REPROLENS_AUDIT_ARGS", "").split()

PAPER_SUFFIXES = {".pdf", ".xml", ".nxml"}
MAX_UPLOAD = 200 * 1024 * 1024
KEEP_JOBS = 6

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_name(name: str) -> str:
    """A filename with the path and anything surprising stripped out."""
    base = Path(name or "upload").name
    cleaned = _SAFE_NAME.sub("_", base).strip(" .") or "upload"
    return cleaned[:120]


@dataclass
class Job:
    id: str
    name: str
    workdir: Path
    supplements: list[str]
    created_at: float = field(default_factory=time.time)
    status: str = "running"  # running | done | failed
    events: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    error: str = ""
    result_dir: Path | None = None
    process: subprocess.Popen | None = None
    changed: threading.Condition = field(default_factory=threading.Condition)

    def push(self, event: dict) -> None:
        with self.changed:
            self.events.append(event)
            self.changed.notify_all()

    def finish(self, status: str, error: str = "") -> None:
        with self.changed:
            self.status = status
            self.error = error
            self.changed.notify_all()


class Registry:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def add(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.id] = job
            finished = [j for j in self.jobs.values() if j.status != "running"]
            finished.sort(key=lambda j: j.created_at)
            while len(self.jobs) > KEEP_JOBS and finished:
                self._remove(finished.pop(0))

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such audit")
        return job

    def remove(self, job_id: str) -> None:
        with self.lock:
            if job := self.jobs.get(job_id):
                self._remove(job)

    def _remove(self, job: Job) -> None:
        if job.process and job.process.poll() is None:
            job.process.terminate()
        shutil.rmtree(job.workdir, ignore_errors=True)
        self.jobs.pop(job.id, None)

    def clear(self) -> None:
        with self.lock:
            for job in list(self.jobs.values()):
                self._remove(job)


registry = Registry()
atexit.register(registry.clear)

app = FastAPI(title="ReproLens", docs_url=None, redoc_url=None)


def find_result(out: Path) -> Path | None:
    """The one directory the audit wrote an assessment into, or None.

    A directory without ``assessment.json`` is NOT a result. The audit can
    produce a partial reading and refuse to score it, and showing that as a
    result would print "could not be read" as "nothing was found".
    """
    if not out.is_dir():
        return None
    produced = [d for d in out.iterdir() if (d / "assessment.json").is_file()]
    return produced[0] if len(produced) == 1 else None


def run(job: Job, paper: Path, supplements: list[Path]) -> None:
    """Run the audit and relay its progress; called on a worker thread."""
    out = job.workdir / "out"
    argv = [
        sys.executable,
        str(AUDIT),
        str(paper),
        "--out",
        str(out),
        "--progress",
        f"--vlm={VLM_BACKEND}",
        *EXTRA_ARGS,
    ]
    for path in supplements:
        argv += ["--supplement", str(path)]

    try:
        job.process = subprocess.Popen(  # noqa: S603 -- fixed argv, paths written by us
            argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        job.finish("failed", f"could not start the audit: {error}")
        return

    assert job.process.stderr is not None
    for line in job.process.stderr:
        line = line.rstrip("\n")
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            job.log.append(line)
            continue
        if isinstance(event, dict) and event.get("event") == "progress":
            job.push(event)
        else:
            job.log.append(line)

    stdout = job.process.stdout.read() if job.process.stdout else ""
    code = job.process.wait()
    job.log.extend(stdout.splitlines()[-40:])

    if code != 0:
        tail = "\n".join(job.log[-30:])
        job.finish("failed", f"the audit exited with status {code}\n{tail}")
        return
    produced = find_result(out)
    if produced is None:
        job.finish("failed", "the audit wrote no assessment; nothing here would be evidence")
        return
    job.result_dir = produced
    job.finish("done")


@app.get("/api/status")
def status() -> dict:
    """What the audit will be able to do right now, asked before anything runs."""
    reason = vlm.blocked(VLM_BACKEND)
    return {
        "vision": {"backend": VLM_BACKEND, "ready": reason is None, "reason": reason or ""},
        "ocr": shutil.which("tesseract") is not None,
        "reduced": EXTRA_ARGS,
    }


@app.post("/api/audits")
async def create(
    paper: UploadFile = File(...),  # noqa: B008 -- FastAPI's declaration style
    supplements: list[UploadFile] = File(default=[]),  # noqa: B008
) -> dict:
    name = safe_name(paper.filename or "paper.pdf")
    if Path(name).suffix.lower() not in PAPER_SUFFIXES:
        raise HTTPException(400, "the paper must be a PDF or a JATS XML file")

    workdir = Path(tempfile.mkdtemp(prefix="reprolens-"))
    incoming = workdir / "incoming"
    incoming.mkdir()
    paper_path = await _save(paper, incoming / name)

    supplement_paths: list[Path] = []
    for upload in supplements:
        if not upload.filename:
            continue
        target = incoming / "supplements" / safe_name(upload.filename)
        target.parent.mkdir(exist_ok=True)
        if target == paper_path:
            continue
        supplement_paths.append(await _save(upload, target))

    job = Job(
        id=uuid.uuid4().hex[:12],
        name=name,
        workdir=workdir,
        supplements=[p.name for p in supplement_paths],
    )
    registry.add(job)
    threading.Thread(target=run, args=(job, paper_path, supplement_paths), daemon=True).start()
    return {"id": job.id, "name": job.name, "supplements": job.supplements}


async def _save(upload: UploadFile, target: Path) -> Path:
    size = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD:
                handle.close()
                shutil.rmtree(target.parent.parent, ignore_errors=True)
                raise HTTPException(413, "that file is larger than 200 MB")
            handle.write(chunk)
    return target


@app.get("/api/audits/{job_id}/events")
async def events(job_id: str) -> StreamingResponse:
    """Server-sent events: every progress line so far, then each new one as it lands."""
    job = registry.get(job_id)

    async def stream():
        sent = 0
        while True:
            with job.changed:
                pending = job.events[sent:]
                status_now = job.status
            for event in pending:
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"
            sent += len(pending)
            if status_now != "running":
                payload = {"status": status_now, "error": job.error}
                yield f"event: end\ndata: {json.dumps(payload)}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/audits/{job_id}")
def result(job_id: str) -> JSONResponse:
    job = registry.get(job_id)
    body: dict = {
        "id": job.id,
        "name": job.name,
        "supplements": job.supplements,
        "status": job.status,
        "error": job.error,
        "log": job.log[-30:],
    }
    if job.status == "done" and job.result_dir is not None:
        body["view"] = view.build(job.result_dir)
    return JSONResponse(body)


@app.get("/api/audits/{job_id}/figures/{filename}")
def figure(job_id: str, filename: str) -> FileResponse:
    job = registry.get(job_id)
    if job.result_dir is None:
        raise HTTPException(404, "no result yet")
    clean = Path(filename).name
    path = job.result_dir / "figures" / clean
    if clean != filename or not path.is_file() or path.suffix.lower() != ".png":
        raise HTTPException(404, "no such figure")
    return FileResponse(path, media_type="image/png")


@app.delete("/api/audits/{job_id}")
def delete(job_id: str) -> dict:
    registry.remove(job_id)
    return {"deleted": job_id}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text())


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("REPROLENS_HOST", "127.0.0.1")
    port = int(os.environ.get("REPROLENS_PORT", "8765"))
    uvicorn.run("app.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
