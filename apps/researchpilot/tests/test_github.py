import base64
import httpx
import pytest

from researchpilot.github import parse_repo, fetch_repository, allowed_file


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://github.com.evil/a/b", "https://evil@github.com/a/b", "https://127.0.0.1/a/b", "https://github.com/a/b/tree/main", "https://github.com/a/b?x=y", "https://github.com/a/.."])
def test_no_arbitrary_hosts_or_paths(url):
    with pytest.raises(ValueError):
        parse_repo(url)


def test_pinned_commit_import_and_symlink_exclusion():
    requests = []
    def respond(request):
        path = request.url.path
        requests.append(path)
        responses = {"/repos/u/r":{"default_branch":"main","private":False},
                     "/repos/u/r/commits/main":{"sha":"abc123","commit":{"tree":{"sha":"tree123"}}},
                     "/repos/u/r/git/trees/tree123":{"tree":[
                         {"path":"README.md","type":"blob","mode":"100644","size":30,"sha":"blob1"},
                         {"path":"secret.txt","type":"blob","mode":"100644","size":30,"sha":"secret"},
                         {"path":"link.py","type":"blob","mode":"120000","size":30,"sha":"link"}],"truncated":False},
                     "/repos/u/r/git/blobs/blob1":{"encoding":"base64","size":30,"content":base64.b64encode(b"python infer.py --input data").decode()}}
        return httpx.Response(200,json=responses[path])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = fetch_repository("https://github.com/u/r",client=client)
    assert result["commit"] == "abc123"
    assert [f["path"] for f in result["files"]] == ["README.md"]
    assert not any("secret" in p or "link" in p for p in requests)
    assert not allowed_file({"path":".env","type":"blob","size":20})


@pytest.mark.parametrize("code", [302,403,404,429,500])
def test_remote_failures_are_actionable(code):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(code))) as client:
        with pytest.raises(ValueError):
            fetch_repository("https://github.com/u/r",client=client)
