#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global configuration class."""


from typing import Any


class App:
    """The global configuration class.

    Contains shared variables or variables which control the operation of the
    bot
    """

    __conf = {}
    __setters = ()

    @staticmethod
    def config(name: str) -> Any:
        """Get a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to get the value for.
        """
        return App.__conf[name]

    @staticmethod
    def set(name: str, value: Any) -> None:
        """Set the value of a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to set a value for.
        value: Any
            The new value of the parameter.
        """
        if name in App.__setters:
            App.__conf[name] = value
        else:
            raise NameError("Name not accepted in set() method")
