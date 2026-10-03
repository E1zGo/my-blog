import httpx
import pytest

from researchpilot.config import Settings
from researchpilot.provider import ModelProvider, ProviderError


def test_embedding_dimension_validation(monkeypatch):
    provider=ModelProvider(Settings(embed_model="test"))
    monkeypatch.setattr(provider,"post",lambda *a:{"data":[{"index":0,"embedding":[1,0]},{"index":1,"embedding":[1]}]})
    with pytest.raises(ProviderError):
        provider.embed(["a","b"])


def test_embedding_order_and_local_endpoint(monkeypatch):
    provider=ModelProvider(Settings(api_base="http://localhost:11434/v1",embed_model="test"))
    monkeypatch.setattr(provider,"post",lambda *a:{"data":[{"index":1,"embedding":[0,1]},{"index":0,"embedding":[1,0]}]})
    assert provider.embed(["a","b"]) == [[1,0],[0,1]]
    with pytest.raises(ProviderError):
        ModelProvider(Settings(api_base="http://remote.example/v1"))


def test_provider_errors_do_not_expose_credentials(monkeypatch):
    provider=ModelProvider(Settings(api_key="TOP_SECRET",model="test"))
    def fail(*args,**kwargs):
        response=httpx.Response(401,request=httpx.Request("POST","https://example.com",headers={"Authorization":"Bearer TOP_SECRET"}))
        raise httpx.HTTPStatusError("TOP_SECRET",request=response.request,response=response)
    monkeypatch.setattr(httpx.Client,"post",fail)
    with pytest.raises(ProviderError) as error:
        provider.chat([],[])
    assert "TOP_SECRET" not in str(error.value)
    assert "401" in str(error.value)
