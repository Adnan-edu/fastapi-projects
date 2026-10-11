from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    id: int
    name: str
    description: Optional[str] = None


@dataclass
class ItemStore:
    _items: dict[int, Item] = field(default_factory=dict)
    _next_id: int = field(default=1)

    def list_items(self) -> list[Item]:
        return list(self._items.values())

    def get_item(self, item_id: int) -> Optional[Item]:
        return self._items.get(item_id)

    def create_item(self, name: str, description: Optional[str] = None) -> Item:
        item = Item(id=self._next_id, name=name, description=description)
        self._items[self._next_id] = item
        self._next_id += 1
        return item


store = ItemStore()


def list_items() -> list[Item]:
    return store.list_items()


def get_item(item_id: int) -> Optional[Item]:
    return store.get_item(item_id)


def create_item(name: str, description: Optional[str] = None) -> Item:
    return store.create_item(name=name, description=description)