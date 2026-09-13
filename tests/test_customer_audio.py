import base64
import io
import wave

import pytest
from fastapi.testclient import TestClient
import api
import config
import customer_audio
from providers.fake_provider import FakeProvider


def payload(raw=b'\xff' * 160):
    return dict(id='utterance', codec='audio/x-mulaw', sample_rate=8000,
                complete=True, mulaw_base64=base64.b64encode(raw).decode())


@pytest.fixture
def client(sqlite_repo, monkeypatch, tmp_path):
    monkeypatch.setenv('CUSTOMER_AUDIO_DIR', str(tmp_path / 'audio'))
    monkeypatch.setattr(api, '_repo', sqlite_repo)
    monkeypatch.setattr(api, '_provider', FakeProvider('hello'))
    monkeypatch.setattr(config, 'API_KEY', 'test-key')
    with TestClient(api.app, headers={'X-API-Key': 'test-key'}) as client:
        yield client


def test_audio_bound_to_message_survives_db_read(client):
    response = client.post('/chat', json={'user_id': 'tester', 'message': 'two porotta', 'customer_audio': payload()})
    assert response.status_code == 200
    sid = response.json()['session_id']
    msgs = client.get(f'/sessions/{sid}/messages').json()
    assert msgs[0]['content'] == 'two porotta'
    clip = msgs[0]['customer_audio']
    assert msgs[1]['customer_audio'] is None
    path = f'/sessions/{sid}/audio/{clip["id"]}'
    assert client.get(path, headers={'X-API-Key': 'wrong'}).status_code == 401
    assert client.get(path+'?format=mulaw').content == b'\xff' * 160
    with wave.open(io.BytesIO(client.get(path).content)) as wav:
        assert (wav.getframerate(), wav.getnframes(), wav.getnchannels()) == (8000, 160, 1)
        assert wav.readframes(160) == b'\x00' * 320
    other = client.post('/chat', json={'user_id': 'other', 'message': 'hi'}).json()['session_id']
    assert client.get(f'/sessions/{other}/audio/{clip["id"]}').status_code == 404
    assert client.get(path+'?format=invalid').status_code == 400
    client.delete(f'/sessions/{sid}')
    assert client.get(path).status_code == 404
    assert not list(customer_audio.directory().glob('*'))


def test_expiry_and_invalid_audio_are_nonfatal(client, monkeypatch):
    response = client.post('/chat', json={'user_id': 'tester', 'message': 'hi', 'customer_audio': payload(b'')})
    assert response.status_code == 200
    sid = response.json()['session_id']
    assert client.get(f'/sessions/{sid}/messages').json()[0]['customer_audio']['status'] == 'unavailable'
    meta = customer_audio.save(payload(), sid)
    monkeypatch.setattr(customer_audio.time, 'time', lambda: meta['expires_at'] + 1)
    with pytest.raises(FileNotFoundError):
        customer_audio.read(sid, meta['id'])
    with pytest.raises(FileNotFoundError):
        customer_audio.read(sid, '../secret')


def test_mulaw_decoder_matches_reference():
    import audioop
    raw = bytes(range(256))
    with wave.open(io.BytesIO(customer_audio.wav_bytes(raw))) as wav:
        assert wav.readframes(256) == audioop.ulaw2lin(raw, 2)
