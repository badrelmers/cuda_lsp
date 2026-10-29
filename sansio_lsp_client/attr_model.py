from __future__ import annotations

import typing as t

import attrs
from cattrs import Converter, override
from cattrs.errors import BaseValidationError
from cattrs.gen import make_dict_structure_fn, make_dict_unstructure_fn

__all__ = [
    "AttrsModel",
    "TypeAdapter",
    "ValidationError",
    "converter",
]

# Create converter instance with better configuration
# forbid_extra_keys = Don't fail on unknown keys from server
converter = Converter(forbid_extra_keys=False)


class ValidationError(ValueError):
    """Lightweight replacement for Pydantic's ValidationError."""

    def __init__(self, message: str, original: BaseValidationError | None = None) -> None:
        super().__init__(message)
        self.original = original


def _register_class(cls: type) -> None:
    if not attrs.has(cls):
        return

    overrides: dict[str, override] = {}

    for field in attrs.fields(cls):
        alias = field.metadata.get("alias")
        private = field.metadata.get("private", False)

        if alias or private:
            overrides[field.name] = override(
                rename=alias,
                omit=private,
            )

    structure_fn = make_dict_structure_fn(cls, converter, **overrides)
    unstructure_fn = make_dict_unstructure_fn(cls, converter, **overrides)

    converter.register_structure_hook(cls, structure_fn)
    converter.register_unstructure_hook(cls, unstructure_fn)


@attrs.define(slots=True)
class AttrsModel:
    """Base class that mimics the minimal Pydantic API we rely on."""

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        super().__init_subclass__(**kwargs)
        _register_class(cls)

    def model_dump(
        self,
        *,
        exclude_unset: bool | None = None,
        exclude_none: bool | None = None,
        exclude: t.Optional[t.Set[str]] = None,
        **_: t.Any,
    ) -> dict[str, t.Any]:
        data: dict[str, t.Any] = converter.unstructure(self)

        if exclude_unset or exclude_none:
            data = {key: value for key, value in data.items() if value is not None}

        if exclude:
            for key in exclude:
                data.pop(key, None)

        return data

    @classmethod
    def model_validate(cls: type["T"], data: t.Any) -> "T":
        try:
            return converter.structure(data, cls)
        except BaseValidationError as exc:  # pragma: no cover - mirrors pydantic API
            raise ValidationError(f"{exc} | payload={data}", exc) from exc


T = t.TypeVar("T")


class TypeAdapter(t.Generic[T]):
    def __init__(self, typ: type[T] | t.Any) -> None:
        self._typ: type[T] | t.Any = typ

    def validate_python(self, data: t.Any) -> T:
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        try:
            return converter.structure(data, self._typ)
        except BaseValidationError as exc:  # pragma: no cover - mirrors pydantic API
            raise ValidationError(f"{exc} | payload={data}", exc) from exc


# Register the base class itself to ensure derived classes inherit proper hooks.
_register_class(AttrsModel)
