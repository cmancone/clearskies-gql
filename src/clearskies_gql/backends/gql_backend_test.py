import unittest
from unittest.mock import MagicMock
from collections import OrderedDict
from types import SimpleNamespace
from .gql_backend import GqlBackend
import clearskies
from clearskies.di import StandardDependencies
from boto3.dynamodb import conditions as dynamodb_conditions
class User(clearskies.Model):
    def __init__(self, gql_backend, columns):
        super().__init__(gql_backend, columns)

    def columns_configuration(self):
        return OrderedDict([
            clearskies.column_types.string('name'),
            clearskies.column_types.string('category_id'),
            clearskies.column_types.integer('age'),
        ])
class Users(clearskies.Models):
    def __init__(self, gql_backend, columns):
        super().__init__(gql_backend, columns)

    def model_class(self):
        return User
class GqlBackendTest(unittest.TestCase):
    def setUp(self):
        self.di = StandardDependencies()

    def test_configure(self):
        environment = SimpleNamespace(get=MagicMock(return_value='https://env.example.com'))
        backend = GqlBackend('requests', environment)
        backend.configure(url='https://example.com', auth='auth')
        self.assertEquals('https://example.com', backend.url)
        self.assertEquals('auth', backend._auth)
        environment.get.assert_not_called()

        backend.configure()
        self.assertEquals('https://env.example.com', backend.url)
        self.assertEquals(None, backend._auth)
        environment.get.assert_called_with('gql_server_url', silent=True)
