from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RawProduct:
    url: str
    name: str
    description: str
    price: Decimal
    hdd_sizes: list[int] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Product:
    name: str
    description: str
    price: Decimal
    colors: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "price": float(self.price),
        }
        if self.colors:
            out["colors"] = self.colors
        return out
