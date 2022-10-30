from clearskies.backends.backend import Backend
from typing import Any, Callable, Dict, List, Tuple
class GqlBackend(Backend):
    _requests = None
    _environment = None
    _auth = None
    url = None

    def __init__(self, requests, environment):
        self._requests = requests
        self._environment = environment

    def configure(self, url=None, auth=None):
        self.url = url
        if not self.url:
            self.url = self._environment.get('gql_server_url', silent=True)
        if not self.url:
            raise ValueError(
                "Failed to find GQL Server URL.  Set it by extending the GqlBackend and setting the 'url' parameter of the configure method, or via the 'gql_server_url' environment variable"
            )
        self._auth = auth

    def records(self, configuration, model, next_page_data=None):
        pass

    def count(self, configuration, model):
        pass

    def create(self, data, model):
        pass

    def update(self, id, data, model):
        pass

    def delete(self, id, model):
        pass

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
