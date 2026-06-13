"""Unit tests for the API key verifier."""

import pytest

from ai_web_search.server import _APIKeyVerifier


@pytest.mark.asyncio
async def test_correct_key_returns_access_token():
    tok = await _APIKeyVerifier("mysecret").verify_token("mysecret")
    assert tok is not None
    assert tok.client_id == "api-client"
    assert tok.token == "mysecret"


@pytest.mark.asyncio
async def test_wrong_key_returns_none():
    assert await _APIKeyVerifier("mysecret").verify_token("wrong") is None


@pytest.mark.asyncio
async def test_empty_token_returns_none():
    assert await _APIKeyVerifier("mysecret").verify_token("") is None


@pytest.mark.asyncio
async def test_different_keys_are_independent():
    v1 = _APIKeyVerifier("key-a")
    v2 = _APIKeyVerifier("key-b")
    assert await v1.verify_token("key-a") is not None
    assert await v1.verify_token("key-b") is None
    assert await v2.verify_token("key-b") is not None
    assert await v2.verify_token("key-a") is None
