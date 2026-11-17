"""The web product, driven through its API.

The audit runs as a real subprocess with the network channels off
(``REPROLENS_AUDIT_ARGS``), so one request finishes in seconds and the test
still exercises the real pipeline: upload, progress stream, result, figure,
delete.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("REPROLENS_AUDIT_ARGS", "--no-repo --no-resolve --no-vlm")

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from app import server  # noqa: E402 -- after the environment is set

PAPER = Path("data/papers/aspen.pdf")


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c
    server.registry.clear()


class TestSafety:
    def test_filenames_lose_their_paths(self):
        assert server.safe_name("../../etc/passwd") == "passwd"
        assert server.safe_name("a b (1).pdf") == "a b _1_.pdf"
        assert server.safe_name("") == "upload"

    def test_a_directory_without_an_assessment_is_not_a_result(self, tmp_path):
        (tmp_path / "paper").mkdir()
        (tmp_path / "paper" / "links.json").write_text("{}")
        assert server.find_result(tmp_path) is None
        (tmp_path / "paper" / "assessment.json").write_text("{}")
        assert server.find_result(tmp_path) == tmp_path / "paper"

    def test_the_paper_must_be_a_paper(self, client):
        r = client.post("/api/audits", files={"paper": ("notes.txt", b"hello", "text/plain")})
        assert r.status_code == 400

    def test_an_unknown_job_is_404(self, client):
        assert client.get("/api/audits/nope").status_code == 404

    def test_this_file_never_reads_the_benchmark(self):
        assert "benchmark" not in Path(server.__file__).read_text().replace(
            "This file never reads\n``benchmark/``; a test enforces it.", ""
        ).lower().replace("benchmark/``", "")


class TestTheStatusPage:
    def test_status_says_what_the_run_can_do(self, client):
        body = client.get("/api/status").json()
        assert set(body["vision"]) == {"backend", "ready", "reason"}
        assert isinstance(body["ocr"], bool)
        assert "--no-vlm" in body["reduced"]

    def test_the_page_is_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Drop a paper here" in r.text
        assert "is ever executed" in r.text


@pytest.mark.skipif(not PAPER.is_file(), reason="no development paper on this machine")
class TestAnAuditEndToEnd:
    def test_upload_follow_result_delete(self, client, tmp_path):
        supplement = tmp_path / "Supplementary_Table_1.csv"
        supplement.write_text("tool,version\nsamtools,1.15\n")
        with PAPER.open("rb") as paper, supplement.open("rb") as supp:
            r = client.post(
                "/api/audits",
                files=[
                    ("paper", (PAPER.name, paper, "application/pdf")),
                    ("supplements", (supplement.name, supp, "text/csv")),
                ],
            )
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["supplements"] == ["Supplementary_Table_1.csv"]

        stages: list[str] = []
        end: dict = {}
        with client.stream("GET", f"/api/audits/{job['id']}/events") as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if "stage" in payload:
                        stages.append(payload["stage"])
                    else:
                        end = payload
        assert end.get("status") == "done", end
        assert stages[0] == "text"
        assert "supplements" in stages
        assert stages[-1] == "done"

        body = client.get(f"/api/audits/{job['id']}").json()
        assert body["status"] == "done"
        v = body["view"]
        assert v["headline"]["coverage"] > 0
        assert any(c["name"] == "supplements" for c in v["channels"])
        # Figures were extracted but not read on a reduced run, and the page says so.
        figures = next(c for c in v["channels"] if c["name"] == "figures")
        assert figures["ran"] is False

        image = next(f["image"] for f in v["figures"] if f["image"])
        assert client.get(f"/api/audits/{job['id']}/figures/{image}").status_code == 200
        assert client.get(f"/api/audits/{job['id']}/figures/../links.json").status_code in (
            404,
            400,
        )

        assert client.delete(f"/api/audits/{job['id']}").json() == {"deleted": job["id"]}
        assert client.get(f"/api/audits/{job['id']}").status_code == 404
