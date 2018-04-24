from typing import NoReturn

from . import template


# pylint: disable=no-self-use, too-many-public-methods
class BaseView:
    def template(self) -> str:
        return self.__class__.__name__.lower()

    def content(self) -> str:
        return template.render(self)

    def page(self) -> str:
        return template.render_name('page', self)

    def prepare(self) -> NoReturn:
        raise NotImplementedError
