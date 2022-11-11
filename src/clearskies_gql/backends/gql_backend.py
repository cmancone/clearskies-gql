from clearskies.backends import ApiBackend
from clearskies.authentication.public import Public
from clearskies.functional import string
from typing import Any, Callable, Dict, List, Tuple
from clearskies.column_types import BelongsTo, HasMany
import json
class GqlBackend(ApiBackend):
    _requests = None
    _environment = None
    _auth = None
    _logging = None
    url = None

    def __init__(self, requests, environment, logging):
        self._requests = requests
        self._environment = environment
        self._logging = logging

    def configure(self, url=None, auth=None):
        self.url = url
        if not self.url:
            self.url = self._environment.get('gql_server_url', silent=True)
        if not self.url:
            raise ValueError(
                "Failed to find GQL Server URL.  Set it by extending the GqlBackend and setting the 'url' parameter of the configure method, or via the 'gql_server_url' environment variable"
            )
        self._auth = auth if auth is not None else Public()

    def records(self, configuration, model, next_page_data=None):
        plural_object_name = string.make_plural(model.table_name())
        search_string = self._build_gql_search_string(configuration.get('wheres'), model)
        gql_lines = ['query Query {', plural_object_name + search_string + '{']
        gql_lines.extend(self._record_selects(configuration, model))
        gql_lines.append('}')
        gql_lines.append('}')
        response = self._execute_gql(gql_lines)
        records = self._map_records_response(response.json(), model)
        return records

    def _record_selects(self, configuration, model):
        lines = []
        if configuration.get('select_all'):
            for column in model.columns().values():
                if column.is_temporary or isinstance(column, HasMany):
                    continue
                if isinstance(column, BelongsTo):
                    parent_id_column_name = column.parent_models.get_id_column_name()
                    lines.append(column.config('model_column_name') + '{' + parent_id_column_name + '}')
                    continue
                lines.append(column.name)
        elif configuration.get('selects'):
            for select in configuration.get('selects'):
                for column_name in select.split():
                    lines.append(column_name)

        return lines

    def _map_records_response(self, json, model):
        if not 'data' in json:
            raise ValueError("Unexpected response from records request")
        plural_object_name = string.make_plural(model.table_name())
        if plural_object_name not in json['data']:
            raise ValueError("Unexpected response from records request")
        return json['data'][plural_object_name]

    def _build_gql_search_string(self, conditions, model):
        if not conditions:
            return ''

        parts = []
        for condition in conditions:
            # we're being really stupid for now
            column_name = condition['column']
            value = json.dumps(condition['values'][0])
            parts.append(f'{column_name}: {value}')

        return '(where: {' + ', '.join(parts) + '})'

    def count(self, configuration, model):
        # cheating badly and ugl-ly
        return len(self.records(configuration, model))

    def create(self, data, model):
        plural_snake_case_name = string.make_plural(model.table_name())
        singular_title_name = string.snake_case_to_title_case(model.table_name())
        plural_title_name = string.make_plural(singular_title_name)
        input_name = f'[{singular_title_name}CreateInput!]!'
        input_variables = {}
        gql_lines = [f'mutation Create{plural_title_name}($input: ' + input_name + ') {']
        gql_lines.append(f'create{plural_title_name}(' + 'input: $input) {')
        gql_lines.append('  info { nodesCreated }')
        for (key, value) in data.items():
            input_variables[key] = value
        gql_lines.append('  }')
        gql_lines.append('}')
        print(gql_lines)
        print({'variables': {'input': input_variables}})
        result = self._execute_gql(
            gql_lines,
            extra_properties={'variables': {
                'input': input_variables
            }},
            operation_name=f'Create{plural_title_name}',
        )

        # now fetch out the newly created record
        id_column_name = model.id_column_name
        results = self.records({
            'table_name':
            model.table_name(),
            'select_all':
            True,
            'wheres': [{
                'column': id_column_name,
                'operator': '=',
                'values': [data[id_column_name]],
            }]
        }, model)
        return results[0]

    def update(self, id, data, model):
        plural_title_name = string.make_plural(string.snake_case_to_title_case(model.table_name()))
        gql_lines = [f'mutation update{plural_title_name}( input: [']
        gql_lines.append('    {')
        for (key, value) in data.items():
            gql_lines.append(f'{key}: {value}')
        gql_lines.append('    }')
        gql_lines.append('] )')
        return self._execute_gql(gql_lines)

    def delete(self, id, model):
        singular_title_name = string.snake_case_to_title_case(model.table_name())
        plural_title_name = string.make_plural(singular_title_name)
        gql_lines = [
            f'mutation Delete{plural_title_name}($where: {singular_title_name}Where) ' + '{',
            f'  delete{plural_title_name}(where: $where) ' + '{',
            '    nodesDeleted',
            '  }',
            '}',
        ]
        where = {
            'variables': {
                'where': {
                    model.id_column_name: id,
                }
            }
        }
        result = self._execute_gql(gql_lines, extra_properties=where, operation_name=f'Delete{plural_title_name}')

    def _execute_gql(self, gql_lines, extra_properties=None, operation_name=None):
        request_json = {"query": ' '.join(gql_lines)}
        if extra_properties:
            request_json = {
                **request_json,
                **extra_properties,
            }
        if operation_name:
            request_json['operation_name'] = operation_name
        self._logging.info(f'Sending the following JSON to {self.url}:')
        self._logging.info(json.dumps(request_json))
        print(json.dumps(request_json))
        return self._execute_request(self.url, 'POST', json=request_json, retry_auth=True)

    def allowed_pagination_keys(self) -> List[str]:
        return ['after']

    def validate_pagination_kwargs(self, kwargs: Dict[str, Any], case_mapping: Callable) -> str:
        extra_keys = set(kwargs.keys()) - set(self.allowed_pagination_keys())
        if len(extra_keys):
            key_name = case_mapping('after')
            return "Invalid pagination key(s): '" + "','".join(extra_keys) + f"'.  Only '{key_name}' is allowed"
        if 'after' not in kwargs:
            key_name = case_mapping('after')
            return f"You must specify '{after}' when setting pagination"
        return ''

    def documentation_pagination_next_page_response(self, case_mapping: Callable) -> List[Any]:
        return [AutoDocInteger(case_mapping('after'), example=10)]

    def documentation_pagination_next_page_example(self, case_mapping: Callable) -> Dict[str, Any]:
        return {case_mapping('after'): 'cursor-param'}

    def documentation_pagination_parameters(self, case_mapping: Callable) -> List[Tuple[Any]]:
        return [(
            AutoDocInteger(case_mapping('after'),
                           example='cursor-param'), 'The next cursor value to return records after'
        )]

    def column_to_backend(self, column, backend_data):
        # the main thing that we need to handle differently are relationships, as GQL has their own
        # formalizm for those.  Let's work our way down the tree.
        if isinstance(column, BelongsTo):
            return self._belongs_to_to_backend(column, backend_data)

        return column.to_backend(backend_data)

    def _belongs_to_to_backend(self, column, backend_data):
        if not backend_data.get(column.name):
            return backend_data

        model_column_name = column.config('model_column_name')
        parent = column.parent_models
        parent_id_column_name = parent.id_column_name
        new_id = backend_data[column.name]
        del backend_data[column.name]

        return {**backend_data, model_column_name: {"connect": {"where": {"node": {parent_id_column_name: new_id}}}}}
