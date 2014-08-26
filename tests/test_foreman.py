import mock

import pytest

from webtest import TestApp

from tornado.web import Application
from tornado.wsgi import WSGIAdapter

from archiver.foreman.views import collect_handlers

from utils.jsons import good


@pytest.fixture(autouse=True)
def patch_push(monkeypatch):
    mock_push = mock.MagicMock()
    monkeypatch.setattr('archiver.foreman.utils.archive.delay', mock_push)
    return mock_push


@pytest.fixture(autouse=True)
def app(request):
    class ProxyHack(object):
    #http://stackoverflow.com/questions/14872829/get-ip-address-when-testing-flask-application-through-nosetests

        def __init__(self, app):
            self.app = app

        def __call__(self, environ, start_response):
            environ['REMOTE_ADDR'] = environ.get('REMOTE_ADDR', '127.0.0.1')
            return self.app(environ, start_response)

    return TestApp(WSGIAdapter(Application(collect_handlers(), debug=True)))


def test_empty(app):
    url = app.app.application.reverse_url('ArchiveHandler')
    ret = app.post(url, expect_errors=True)
    assert ret.status_code == 400


def test_empty_put(app):
    url = app.app.application.reverse_url('ArchiveHandler')
    ret = app.put(url, expect_errors=True)
    assert ret.status_code == 400


def test_empty_json(app):
    url = app.app.application.reverse_url('ArchiveHandler')
    ret = app.post_json(url, {}, expect_errors=True)
    assert ret.status_code == 400


def test_good_json(app, patch_push):
    url = app.app.application.reverse_url('ArchiveHandler')
    ret = app.post_json(url, good)
    assert ret.status_code == 201
    assert patch_push.call_args[0][0].raw_json == good['container']
