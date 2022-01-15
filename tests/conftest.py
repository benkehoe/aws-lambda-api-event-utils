import pytest

import urllib
import dataclasses
import json
import functools

import requests


def pytest_addoption(parser):
    parser.addoption("--rest-api")
    parser.addoption("--http-api")


@dataclasses.dataclass
class Config:
    rest_api: str
    http_api: str

    def _join(self, base: str, path: str) -> str:
        base = base.rstrip("/")
        path = path.lstrip("/")
        return base + "/" + path

    def rest_url(self, path: str) -> str:
        if not self.rest_api:
            raise ValueError("REST API not set")
        return self._join(self.rest_api, path)

    def http_url(self, path: str) -> str:
        if not self.http_api:
            raise ValueError("HTTP API not set")
        return self._join(self.http_api, path)


@pytest.fixture(scope="session")
def config(pytestconfig):
    rest_api = pytestconfig.getoption("--rest-api", skip=True)
    http_api = pytestconfig.getoption("--http-api", skip=False)
    return Config(
        rest_api=rest_api,
        http_api=http_api,
    )


class Caller:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()

    def __getattr__(self, name: str):
        method = name.upper()
        return functools.partial(self.call, method=method)

    def call(
        self,
        *,
        type,
        path,
        method,
        validation=None,
        params=None,
        body=None,
        headers: dict = None,
        body_validation=None,
    ):
        if type.upper() == "REST":
            url = self.config.rest_url(path)
        elif type.upper() == "HTTP":
            url = self.config.http_url(path)
        else:
            raise ValueError(type)

        if headers:
            headers = headers.copy()
        else:
            headers = {}

        if not validation:
            validation = {}
        headers["x-validation"] = json.dumps(validation)

        if body_validation:
            headers["x-body-validation"] = json.dumps(body_validation)

        args = dict(
            method=method,
            url=url,
            params=params,
            headers=headers,
        )
        if body:
            args["json"] = body

        request = requests.Request(**args)
        prepared_request = request.prepare()

        print(">" * 20)
        print(type, prepared_request.method, prepared_request.url)
        for key, value in prepared_request.headers.items():
            print(f"{key}: {value}")
        if prepared_request.body:
            print(prepared_request.body)

        print("-" * 20)

        response = self.session.send(prepared_request)

        print(response.status_code, response.reason)
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)

        print("<" * 20)

        return response


@pytest.fixture(scope="function")
def caller(config):
    return Caller(config)
