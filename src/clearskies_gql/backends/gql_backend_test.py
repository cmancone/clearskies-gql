import unittest
from unittest.mock import MagicMock
from collections import OrderedDict
from types import SimpleNamespace
from .gql_backend import GqlBackend
import clearskies
import logging
from clearskies.di import StandardDependencies
class User(clearskies.Model):
    def __init__(self, gql_backend, columns):
        super().__init__(gql_backend, columns)

    def columns_configuration(self):
        return OrderedDict([
            clearskies.column_types.string('name'),
            clearskies.column_types.string('category_id'),
            clearskies.column_types.integer('age'),
        ])
class GqlBackendTest(unittest.TestCase):
    def setUp(self):
        self.api_response = {"status": "success", "data": {"id": 5}}
        response = type('', (), {'ok': True, 'json': lambda: self.api_response, 'content': 'sup'})
        self.requests = type('', (), {
            'request': MagicMock(return_value=response),
        })()
        self.auth = type('', (), {
            'headers': MagicMock(return_value={'Authorization': 'Bearer: asdfer'}),
        })()

        self.di = StandardDependencies()
        self.di.bind('requests', self.requests)
        self.di.bind('environment', 'environment')
        self.di.bind('logging', logging)

        self.gql_backend = self.di.build(GqlBackend)
        self.gql_backend.configure(url='https://example.gql', auth=self.auth)

        self.di.bind('gql_backend', self.gql_backend)

        self.user = self.di.build(User)

    def test_configure(self):
        environment = SimpleNamespace(get=MagicMock(return_value='https://env.example.com'))
        backend = GqlBackend('requests', environment, logging)
        backend.configure(url='https://example.com', auth='auth')
        self.assertEquals('https://example.com', backend.url)
        self.assertEquals('auth', backend._auth)
        environment.get.assert_not_called()

        backend.configure()
        self.assertEquals('https://env.example.com', backend.url)
        self.assertEquals(None, backend._auth)
        environment.get.assert_called_with('gql_server_url', silent=True)

    def test_query(self):
        response = type('', (), {'ok': True, 'json': lambda: {"data": [{"id": 5}, {"id": 10}]}})
        self.requests.request = MagicMock(return_value=response)
        records = self.gql_backend.records(
            {
                'wheres': [
                    {
                        'column': 'age',
                        'operator': '=',
                        'values': [5],
                        'parsed': ''
                    },
                    {
                        'column': 'id',
                        'operator': '=',
                        'values': [123],
                        'parsed': ''
                    },
                ],
                'select_all':
                True,
        #'sorts': [{
        #'column': 'age',
        #'direction': 'desc'
        #}],
        #'pagination': {
        #'start': 200
        #},
                'limit':
                100,
            },
            self.user
        )
        self.assertEquals([{'id': 5}, {'id': 10}], records)
        self.requests.request.assert_called_with(
            'POST',
            'https://example.gql',
            headers={'Authorization': 'Bearer: asdfer'},
            json={'query': 'query Query { users(age: 5, id: 123){ id name category_id age } }'}
        )
