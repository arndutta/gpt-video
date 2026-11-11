"""Upload boundary, publication, and metadata-privacy checks through the ASGI app."""

import json

import pytest

from test_grounding_api import Embedder, application, complete, retrieve, upload


@pytest.mark.parametrize("origin", ["https://outside.example", "null", "http://127.0.0.1:5173.outside.example"])
def test_cross_site_browser_forms_cannot_publish_local_documents(tmp_path, origin):
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", headers={"origin": origin},
                               files={"file": ("policy.md", b"Margin policy", "text/markdown")})
        assert response.status_code == 403
        assert client.get("/api/grounding/uploads").json()["items"] == []


def test_local_browser_form_is_accepted(tmp_path):
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", headers={"origin": "http://127.0.0.1:5173"},
                               files={"file": ("policy.md", b"Margin policy", "text/markdown")})
        assert response.status_code == 202
        assert complete(client, response.json())["status"] == "ready"


@pytest.mark.parametrize("filename,content,fields,status", [
    ("policy.pdf", b"Margin policy", {}, 415),
    ("policy.txt", b"", {}, 422),
    ("policy.md", b" \n\t", {}, 422),
    ("policy.txt", b"margin \xff policy", {}, 422),
    ("policy.txt", b"margin\x00policy", {}, 422),
    ("policy.txt", b"Margin policy", {"collection": "secret-collection"}, 422),
    ("policy.txt", b"Margin policy", {"source_id": "../escape"}, 422),
    ("policy.txt", b"Margin policy", {"title": "   "}, 422),
    ("policy.txt", b"Margin policy", {"version": "   "}, 422),
    ("policy.txt", b"Margin policy", {"api_key": "UPLOAD-PRIVATE-39012"}, 422),
    ("policy.txt", b"x" * 2_000_001, {}, 413),
])
def test_invalid_uploads_do_not_create_jobs_or_publish_documents(tmp_path, filename, content,
                                                               fields, status):
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", data=fields,
                               files={"file": (filename, content, "text/plain")})
        assert response.status_code == status, response.text
        assert "UPLOAD-PRIVATE-39012" not in response.text
        assert client.get("/api/grounding/uploads").json()["items"] == []
        stats = client.get("/api/grounding/collections").json()
        assert stats["corpus_version"] == 0
        assert all(item["document_count"] == item["chunk_count"] == 0 for item in stats["items"])


def test_missing_or_string_file_duplicate_fields_and_extra_files_are_rejected(tmp_path):
    with application(tmp_path) as (client, _):
        responses = [
            client.post("/api/grounding/uploads", files={
                "file": (None, "UPLOAD-PRIVATE-39012")}),
            client.post("/api/grounding/uploads", files={
                "document": ("policy.txt", b"margin policy", "text/plain")}),
            client.post("/api/grounding/uploads", files=[
                ("file", ("policy.txt", b"margin policy", "text/plain")),
                ("file", ("other.txt", b"other policy", "text/plain"))]),
            client.post("/api/grounding/uploads", files=[
                ("file", ("policy.txt", b"margin policy", "text/plain")),
                ("source_id", (None, "first-source")),
                ("source_id", (None, "second-source"))]),
        ]
        assert all(response.status_code == 422 for response in responses), [
            (response.status_code, response.text) for response in responses]
        assert all("UPLOAD-PRIVATE-39012" not in response.text for response in responses)
        assert client.post("/api/grounding/uploads", data={"file": "text"}).status_code == 415
        assert client.post("/api/grounding/uploads", content=b"", headers={
            "content-type": "multipart/form-data-extra; boundary=example"}).status_code == 415
        assert client.get("/api/grounding/uploads").json()["items"] == []


def test_upload_defaults_and_pathlike_filenames_never_become_filesystem_paths(tmp_path):
    with application(tmp_path) as (client, _):
        for filename, leaf in (("../../outside.txt", "outside.txt"),
                               ("..\\..\\windows.md", "windows.md")):
            response = client.post("/api/grounding/uploads", files={
                "file": (filename, b"Margin policy preserves cost recovery.", "text/plain")})
            assert response.status_code == 202, response.text
            job = complete(client, response.json())
            assert job["status"] == "ready", job
            assert job["filename"] == leaf and job["collection"] == "user_uploads"
            assert job["source_id"] and job["title"]
        context = retrieve(client)
        assert {chunk["collection"] for chunk in context["chunks"]} == {"user_uploads"}
        for chunk in context["chunks"]:
            assert chunk["source_uri"] and ".." not in chunk["source_uri"]
            assert "\\" not in chunk["source_uri"]
        assert not list(tmp_path.rglob("outside.txt"))
        assert not list(tmp_path.rglob("windows.md"))
        assert not (tmp_path.parent / "outside.txt").exists()


def test_request_cap_rejects_content_length_and_streams_without_content_length(tmp_path):
    with application(tmp_path) as (client, _):
        claimed = client.post("/api/grounding/uploads", content=b"tiny", headers={
            "content-length": "4000000", "content-type": "multipart/form-data; boundary=large"})
        assert claimed.status_code == 413
        boundary = b"--large\r\nContent-Disposition: form-data; name=\"file\"; filename=\"large.txt\"\r\n\r\n"
        chunks = iter([boundary, *([b"x" * 100_000] * 30), b"\r\n--large--\r\n"])
        streamed = client.post("/api/grounding/uploads", content=chunks,
                               headers={"content-type": "multipart/form-data; boundary=large"})
        assert "content-length" not in streamed.request.headers
        assert streamed.status_code == 413, streamed.text
        assert client.get("/api/grounding/uploads").json()["items"] == []


@pytest.mark.parametrize("content_type,body", [
    ("multipart/form-data", b"not a multipart document"),
    ("multipart/form-data; boundary=expected", b"--wrong\r\nbody\r\n--wrong--\r\n"),
])
def test_malformed_multipart_is_rejected_without_server_error_or_job(tmp_path, content_type, body):
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", content=body,
                               headers={"content-type": content_type})
        assert response.status_code == 422, response.text
        assert client.get("/api/grounding/uploads").json()["items"] == []


@pytest.mark.parametrize("suffix", [
    b"",  # File content ends before any closing boundary.
    b"\r\n--b\r\n",  # Complete file part followed by a missing final part.
    b'\r\n--b\r\nContent-Disposition: form-data; name="collection"\r\n\r\npricing_policy',
])
def test_truncated_multipart_never_discards_metadata_and_publishes_partial_upload(tmp_path,
                                                                                monkeypatch,
                                                                                suffix):
    from starlette import formparsers

    temporary_files, original = [], formparsers.SpooledTemporaryFile

    def track_file(*args, **kwargs):
        stream = original(*args, **kwargs)
        temporary_files.append(stream)
        return stream

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", track_file)
    prefix = b'--b\r\nContent-Disposition: form-data; name="file"; filename="policy.txt"\r\n\r\nMargin policy.'
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", content=prefix + suffix,
                               headers={"content-type": "multipart/form-data; boundary=b"})
        assert response.status_code == 422, response.text
        assert temporary_files and all(stream.closed for stream in temporary_files)
        assert client.get("/api/grounding/uploads").json()["items"] == []
        stats = client.get("/api/grounding/collections").json()
        assert stats["corpus_version"] == 0
        assert all(item["document_count"] == 0 for item in stats["items"])


def test_valid_multipart_termination_accepts_legal_epilogue(tmp_path):
    body = (b'--b\r\nContent-Disposition: form-data; name="file"; filename="policy.txt"\r\n\r\n'
            b'Margin policy.\r\n--b--\r\nA legal MIME epilogue.\r\n')
    with application(tmp_path) as (client, _):
        response = client.post("/api/grounding/uploads", content=body,
                               headers={"content-type": "multipart/form-data; boundary=b"})
        assert response.status_code == 202, response.text
        job = complete(client, response.json())
        assert job["status"] == "ready", job
        assert {chunk["text"] for chunk in retrieve(client)["chunks"]} == {"Margin policy."}


def test_failed_upload_has_safe_status_and_preserves_previous_published_context(tmp_path):
    marker = "DOCUMENT-PRIVATE-784513"
    credential = "PROVIDER-CREDENTIAL-37480"

    class FailingEmbedder(Embedder):
        fail = False

        def embed(self, texts):
            if self.fail:
                raise RuntimeError(f"{credential}: provider echoed {texts!r}")
            return super().embed(texts)

    embedder = FailingEmbedder()
    with application(tmp_path, embedder) as (client, _):
        first = complete(client, upload(client))
        assert first["status"] == "ready", first
        original = retrieve(client)
        embedder.fail = True
        failed = complete(client, upload(client, f"New margin policy {marker}.", version="v2"))
        assert failed["status"] == "failed" and failed["error_code"] and failed["error"]
        assert failed["result"] is None and failed["completed_at"]
        assert marker not in json.dumps(failed) and credential not in json.dumps(failed)
        embedder.fail = False
        assert retrieve(client) == original
        stats = client.get("/api/grounding/collections").json()
        assert stats["corpus_version"] == original["corpus_version"]
        assert sum(item["document_count"] for item in stats["items"]) == 1
        audit = client.get("/api/audit").text
        assert marker not in audit and credential not in audit
    assert marker not in (tmp_path / "telemetry.jsonl").read_text()
    assert credential not in (tmp_path / "telemetry.jsonl").read_text()
    for path in tmp_path.glob("app.db*"):
        assert marker.encode() not in path.read_bytes()
        assert credential.encode() not in path.read_bytes()


def test_conflicting_immutable_version_is_a_failed_job_without_replacing_context(tmp_path):
    with application(tmp_path) as (client, _):
        first = complete(client, upload(client))
        assert first["status"] == "ready", first
        original = retrieve(client)
        conflict = complete(client, upload(client, "Different margin policy with same version."))
        assert conflict["status"] == "failed" and conflict["error_code"]
        assert retrieve(client) == original
        assert client.get("/api/grounding/collections").json()["corpus_version"] == original["corpus_version"]
