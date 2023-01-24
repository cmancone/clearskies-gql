from clearskies.column_types.string import String
from clearskies.autodoc.schema import Array as AutoDocArray
from clearskies.autodoc.schema import Object as AutoDocObject
from clearskies.autodoc.schema import String as AutoDocString
from collections import OrderedDict
class Connection(String):
    """
    Controls a connection between two nodes in a GraphQL system.

    In principal, you can think of this like a standard many-to-many relationship in any other
    database.  However, GraphQL handles the connection information differently enough that it's
    easier to just give it its own class.
    """
    required_configs = [
        'related_models_class',
    ]

    my_configs = [
        'readable_related_columns',
        'own_id_column_name',
        'related_id_column_name',
        'is_readable',
        'reverse_connection_name',
    ]

    def __init__(self, di):
        self.di = di

    @property
    def is_readable(self):
        is_readable = self.config('is_readable', True)
        # default is_readable to False
        return True if (is_readable and is_readable is not None) else False

    def _check_configuration(self, configuration):
        super()._check_configuration(configuration)
        self.validate_models_class(configuration['related_models_class'])
        error_prefix = f"Configuration error for '{self.name}' in '{self.model_class.__name__}':"
        if configuration.get('reverse_connection_name'):
            reverse_connection_name = configuration.get('reverse_connection_name')
            related_columns = self.di.build(configuration['related_models_class'],
                                            cache=True).raw_columns_configuration()
            if reverse_connection_name not in related_columns:
                related_class_name = configuration['related_models_class'].__name__
                raise ValueError(
                    f"{error_prefix} reverse_connection_name of '{reverse_connection_name}' is invalid because there is not a matching column in the related model class, '{related_class_name}', with this name."
                )
        if configuration.get('is_readable'):
            related_columns = self.di.build(configuration['related_models_class'],
                                            cache=True).raw_columns_configuration()
            if not 'readable_related_columns' in configuration:
                raise ValueError(f"{error_prefix} must provide 'readable_related_columns' if is_readable is set")
            readable_related_columns = configuration['readable_related_columns']
            if not hasattr(readable_related_columns, '__iter__'):
                raise ValueError(
                    f"{error_prefix} 'readable_related_columns' should be an iterable " + \
                    'with the list of child columns to output.'
                )
            if isinstance(readable_related_columns, str):
                raise ValueError(
                    f"{error_prefix} 'readable_related_columns' should be an iterable " + \
                    'with the list of child columns to output.'
                )
            for column_name in readable_related_columns:
                if column_name not in related_columns:
                    raise ValueError(
                        f"{error_prefix} 'readable_related_columns' references column named '{column_name}' but this" + \
                        'column does not exist in the related model class.'
                    )

    def _finalize_configuration(self, configuration):
        related_models = self.di.build(configuration['related_models_class'], cache=True)
        return {
            **{
                'own_id_column_name': self.model_class.id_column_name,
                'related_id_column_name': related_models.get_id_column_name(),
                'reverse_connection_name': self.name,
            },
            **super()._finalize_configuration(configuration),
        }

    @property
    def related_models(self):
        return self.di.build(self.config('related_models_class'), cache=True)

    @property
    def own_models(self):
        return self.di.build(self.model_class, cache=True)

    @property
    def related_columns(self):
        return self.related_models.model_columns

    def input_error_for_value(self, value, operator=None):
        if type(value) != list:
            return f'{self.name} should be a list of ids'
        related_models = self.related_models
        related_id_column_name = self.config('related_id_column_name')
        for id_to_check in value:
            if type(id_to_check) != str:
                return f'Invalid selection for {self.name}: all values must be strings'
            if not len(related_models.where(f"{related_id_column_name}={id_to_check}")):
                return f"Invalid selection for {self.name}: record {id_to_check} does not exist"
        return ''

    def can_provide(self, column_name):
        return column_name == self.name

    def provide(self, data, column_name):
        # in order to find our related models we need to search on the other class, which means that it needs to
        # have a similarly-configured column
        related_models = self.related_models
        reverse_connection_name = self.config('reverse_connection_name')
        if reverse_connection_name not in related_models.columns():
            related_models_class_name = self.config('related_models_class').__name__
            raise ValueError(
                f"Cannot return '{self.name}' for model '{self.model_class.__name__}' because the reverse connection from the related model, '{related_models_class_name}', cannot be found.  Either specify 'reverse_connection_name' in column '{self.name}' for model '{self.model_class.__name__}' or ensure they use the same column name for the connecting relationship."
            )

        id_column_name = related_models.columns()[reverse_connection_name].config('related_id_column_name')
        if id_column_name not in data:
            related_models_class_name = self.config('related_models_class').__name__
            raise ValueError(
                f"Cannot return '{self.name}' for model '{self.model_class.__name__}' because the related model, '{related_models_class_name}' is configured to use an id column of '{id_column_name}' but this column does not appear to exist for model '{self.model_class.__name__}'"
            )
        id = data[id_column_name]
        return related_models.where(f'{reverse_connection_name}={id}')

    def to_backend(self, data):
        # we can't persist our mapping data to the database directly, so remove anything here
        # and take care of things in post_save
        if self.name in data:
            del data[self.name]
        return data

    def post_save(self, data, model, id):
        # if our incoming data is not in the data array or is None, then nothing has been set and we do not want
        # to make any changes
        if self.name not in data or data[self.name] is None:
            return data

        # figure out what ids need to be created or deleted from the pivot table.
        own_id_column_name = self.config('own_id_column_name')
        related_id_column_name = self.config('related_id_column_name')
        if not model.exists:
            old_ids = set()
        else:
            old_ids = set([
                getattr(related_model, related_id_column_name) for related_model in getattr(model, self.name)
            ])

        # and the ids that we want to exist now.
        new_ids = set(data[self.name])
        to_delete = old_ids - new_ids
        to_create = new_ids - old_ids
        if to_delete:
            # since this column is specific to GQL, we're going to cheat and just invoke the backend directly.
            # it's just easier that way.  This will make testing slightly more tricky :shrug:
            model._backend.disconnect(own_id_column_name, id, related_id_column_name, to_delete, self.name, model)

        if to_create:
            # since this column is specific to GQL, we're going to cheat and just invoke the backend directly.
            # it's just easier that way.  This will make testing slightly more tricky :shrug:
            model._backend.connect(own_id_column_name, id, related_id_column_name, to_create, self.name, model)

        return data
