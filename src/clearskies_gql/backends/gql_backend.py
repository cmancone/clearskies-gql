from clearskies.backends import ApiBackend
from clearskies.authentication.public import Public
from clearskies.functional import string
from typing import Any, Callable, Dict, List, Tuple
from clearskies.column_types import BelongsTo, HasMany
from ..column_types import Connection
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
        camel_case_name = string.snake_case_to_camel_case(model.table_name())
        plural_object_name = string.make_plural(camel_case_name)
        title_name = string.snake_case_to_title_case(model.table_name())
        search_values = self._build_gql_search_string(configuration.get('wheres'), model)
        where_type_declaration = ''
        where_param_declaration = ''
        if search_values:
            where_type_declaration = '($where: ' + title_name + 'Where)'
            where_param_declaration = '(where: $where)'
        gql_lines = [
            f'query {plural_object_name}{where_type_declaration}' + ' {',
            f'  {plural_object_name}{where_param_declaration}' + ' {',
            "\n    ".join(self._record_selects(configuration, model)), '  }'
            '}'
        ]
        if search_values:
            extra_properties = {'variables': {'where': search_values}}
        else:
            extra_properties = None
        response = self._execute_gql(gql_lines, extra_properties=extra_properties)
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
                    lines.append(column.name + '{' + parent_id_column_name + '}')
                    continue
                if isinstance(column, Connection):
                    if not column.is_readable:
                        continue
                    lines.append(column.name + '{' + ' '.join(column.config('readable_related_columns')) + '}')
                    continue
                lines.append(column.name)
        elif configuration.get('selects'):
            for select in configuration.get('selects'):
                for column_name in select.split():
                    lines.append(column_name)

        return lines

    def _map_records_response(self, json, model):
        if 'data' not in json:
            raise ValueError("Unexpected response from records request")
        plural_object_names = [
            string.make_plural(model.table_name()),
            string.make_plural(string.snake_case_to_camel_case(model.table_name())),
        ]
        for plural_object_name in plural_object_names:
            if plural_object_name in json['data']:
                return json['data'][plural_object_name]
        raise ValueError("Unexpected response from records request")

    def _build_gql_search_string(self, conditions, model):
        if not conditions:
            return {}

        search_values = {}
        columns = model.columns()
        for condition in conditions:
            # we're being really stupid for now
            column_name = condition['column']
            value = condition['values'][0]
            if isinstance(columns.get(column_name), BelongsTo):
                parent_id_column_name = columns.get(column_name).parent_models.id_column_name
                search_values[f'{column_name}_SOME'] = {parent_id_column_name: value}
            elif isinstance(columns.get(column_name), Connection):
                related_id_column_name = columns.get(column_name).config('related_id_column_name')
                search_values[f'{column_name}_SOME'] = {related_id_column_name: value}
            else:
                search_values[column_name] = value

        return search_values

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
        if not data:
            return model.data

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

    def connect(
        self, from_record_id_column_name, from_record_id, to_record_id_column_name, to_record_ids, connection_name,
        model
    ):
        singular_title_name = string.snake_case_to_title_case(model.table_name())
        plural_title_name = string.make_plural(singular_title_name)
        gql_lines = [
            f'mutation Mutation($connect: {singular_title_name}ConnectInput, $where: {singular_title_name}Where) ' +
            '{',
            f'  update{plural_title_name}(connect: $connect, where: $where) ' + '{',
            '    info { relationshipsCreated }',
            '  }',
            '}',
        ]
        connection_entries = []
        # could probably make this a one-liner but it would be harder to read
        for to_record_id in to_record_ids:
            connection_entries.append({'where': {'node': {to_record_id_column_name: to_record_id}}})
        query_data = {
            'variables': {
                'connect': {
                    connection_name: connection_entries,
                },
                'where': {
                    from_record_id_column_name: from_record_id,
                },
            }
        }
        self._execute_gql(gql_lines, extra_properties=query_data)

    def disconnect(
        self, from_record_id_column_name, from_record_id, to_record_id_column_name, to_record_ids, connection_name,
        model
    ):
        singular_title_name = string.snake_case_to_title_case(model.table_name())
        plural_title_name = string.make_plural(singular_title_name)
        gql_lines = [
            f'mutation Mutation($disconnect: {singular_title_name}DisconnectInput, $where: {singular_title_name}Where) '
            + '{',
            f'  update{plural_title_name}(disconnect: $disconnect, where: $where) ' + '{',
            '    info { relationshipsDeleted }',
            '  }',
            '}',
        ]
        disconnection_entries = []
        # could probably make this a one-liner but it would be harder to read
        for to_record_id in to_record_ids:
            disconnection_entries.append({'where': {'node': {to_record_id_column_name: to_record_id}}})
        query_data = {
            'variables': {
                'disconnect': {
                    connection_name: disconnection_entries,
                },
                'where': {
                    from_record_id_column_name: from_record_id,
                },
            }
        }
        self._execute_gql(gql_lines, extra_properties=query_data)

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
        return self._execute_request(self.url, 'POST', json=request_json)

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

        parent = column.parent_models
        parent_id_column_name = parent.id_column_name
        new_id = backend_data[column.name]
        del backend_data[column.name]

        return {**backend_data, column.name: {"connect": {"where": {"node": {parent_id_column_name: new_id}}}}}
