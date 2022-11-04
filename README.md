# clearskies-gql

clearskies bindings for Graph QL.  While this may eventually include handlers to create GQL servers, the current focus is just on a backend to interact with GQL servers.

# Installation, Documentation, and Usage

To install:

```
pip3 install clear-skies-gql
```

# Usage

### Example

Include this in your binding modules, extend it if you need to specify authentication, and then use it in your models.

```
import clearskies
import clearskies_gql

def process_pets_from_gql(pets):
    for pet in pets.where('name=fido'):
        print(pet.species)

class GqlBackendWithAuth(clearskies_gql.backends.GqlBackend):
    def __init__(self, requests, environment, logging, my_auth_method):
        super().__init__(requests, environment, logging)
        self.configure(
            url='https://gql.server.example.com',
            auth=my_auth_method,
        )

class Pet(clearskies.Model):
    def __init__(self, gql_backend_with_auth, columns):
        super().__init__(gql_backend_with_auth, columns)

    def columns_configuration(self):
        return OrderedDict([
            clearskies.column_types.string('name'),
            clearskies.column_types.string('species'),
        ])

process_pets = clearskies.Application(
    clearskies.handlers.Callable,
    {'callable': process_pets_from_gql},
    binding_modules=[clearskies_gql],
    binding_classes=[Pet, GqlBackendWithAuth],
)
```

Then just wire up your application to a context and you're ready to go!

### Record name

`clear-skies-gql` will use the pluralized and snake_case version of the model class name as the descriptor of the records in GQL, e.g. the above model class results in this query:

```
query Query {
  pets {
    name
    species
  }
}
```

But you can override this behavior by specifying the table name for your model, e.g.:

```
class Pet(clearskies.Model):
    def __init__(self, gql_backend_with_auth, columns):
        super().__init__(gql_backend_with_auth, columns)

    @classmethod
    def table_name(cls):
        return 'whateverYouWant'

    def columns_configuration(self):
        return OrderedDict([
            clearskies.column_types.string('name'),
            clearskies.column_types.string('species'),
        ])
```

results in this query:

```
query Query {
  whateverYouWant {
    name
    species
  }
}
```

### Server URL

You can also specify the URL to the GQL server by setting the `gql_server_url` environment variable.  If your gql server doesn't require authentication, then you can use the graphql backend directly:

```
# note: requires the gql_server_url environment variable to point to the server

class Pet(clearskies.Model):
    def __init__(self, gql_backend, columns):
        super().__init__(gql_backend, columns)

    def columns_configuration(self):
        return OrderedDict([
            clearskies.column_types.string('name'),
            clearskies.column_types.string('species'),
        ])
```
