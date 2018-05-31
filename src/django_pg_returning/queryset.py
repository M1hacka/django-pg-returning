from collections import namedtuple

from django.db.models.query import RawQuerySet
from django.db import router
from typing import Any, Union, List, Dict, Tuple


class ReturningQuerySet(RawQuerySet):
    """
    This query set doesn't give opportunity to make database operations.
    But it:
    1) Executes query "not lazy", but when it is called. It is correct for update queries
    2) Caches the result. Duplicate data iteration wouldn't cause duplicate query
    3) Adds additional methods on results
    4) Returns Database to write, not to read as .db
    """
    def __init__(self, *args, **kwargs):
        # A list of fileds, fetched by returning statement, in order to form values_list
        self._fields = kwargs.pop('fields')

        super(ReturningQuerySet, self).__init__(*args, **kwargs)

        # HACK Using methods create a new RawQuerySet, based on current data without calling it.
        # I use it here in order to iterate with super().__iter__ method.
        self._result_cache = list(super(ReturningQuerySet, self).using(self.db))

    def __len__(self):
        return len(self._result_cache)

    def __iter__(self):
        return iter(self._result_cache)

    def __getitem__(self, k):
        return self._result_cache[k]

    @property
    def db(self):  # type: () -> str
        return self._db or router.db_for_write(self.model, **self._hints)

    def using(self, alias):
        """
        This method is used with "lazy" RawQuerySet.
        It can't be used here, as returning statement is executed without "laziness", when it is called.
        :param alias:
        :return:
        """
        raise NotImplementedError('ReturningQuerySet doesn\'t support changing db alias after data is fetched')

    def count(self):  # type: () -> int
        """
        Returns number of records, retrieved by query
        :return: Integer
        """
        return len(self._result_cache)

    def values(self, *fields):  # type: (*str) -> List[Dict[str, Any]]
        """
        This method works like django.db.models.QuerySet.values, but:
        1) Returns a list of dicts, which can not be used as QuerySet any more
        2) Works with cached results only. Doesn't execute a query to database
        3) Raises exception if fetched fields are not the ones, fetched in the query
        :param fields: Fields to get. If not given, all fields are fetched.
        :return: A list of values dicts
        """
        fields = fields or self._fields
        return [{f: getattr(item, f) for f in fields} for item in self._result_cache]

    def values_list(self, *fields, **kwargs):  # type: (*str, **dict) -> List[Union[Tuple[Any], Any]]
        """
        This method works like django.db.models.QuerySet.values_list, but:
        1) Returns a list of dicts, which can not be used as QuerySet any more
        2) Works with cached results only. Doesn't execute a query to database
        3) Raises exception if fetched fields are not the ones, fetched in the query
        :param fields: Field names to get
        :param flat: Boolean. If fields has only 1 field and flat is True,
            returns a list of values, not a list of tuples.
            This flag can't be set together with named.
        :param named: Boolean. If set, returns a collections.namedtuple instance.
            This flag can't be set together with flat.
        :return: A list of values tuples or values if flat is True
        """
        flat = kwargs.pop('flat', False)
        named = kwargs.pop('named', False)

        if not fields:
            raise TypeError("'fields' parameter is required.")
        if flat and named:
            raise TypeError("'flat' and 'named' can't be used together.")
        if flat and len(fields) > 1:
            raise TypeError("'flat' is not valid when values_list is called with more than one field.")
        if kwargs:
            raise ValueError('Unexpected keyword arguments to values_list: %s' % (list(kwargs),))

        if flat:
            return [getattr(item, fields[0]) for item in self._result_cache]
        elif named:
            Row = namedtuple('Row', fields)
            return [Row(*[getattr(item, f) for f in fields]) for item in self._result_cache]
        else:
            return [tuple(getattr(item, f) for f in fields) for item in self._result_cache]