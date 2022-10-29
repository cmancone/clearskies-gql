import unittest
from unittest.mock import MagicMock
from collections import OrderedDict
from types import SimpleNamespace
from .gql_backend import GqlBackend
import clearskies
from ..di import StandardDependencies
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
