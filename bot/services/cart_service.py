from typing import Any


class CartService:
    def __init__(self, data: dict):
        self._data = data

    def _cart(self) -> dict:
        return self._data.setdefault("cart", {})

    def add(self, product_id: int, price: float, name: str) -> None:
        cart = self._cart()
        key = str(product_id)
        if key in cart:
            cart[key]["qty"] += 1
        else:
            cart[key] = {"qty": 1, "price": price, "name": name}

    def remove(self, product_id: int) -> None:
        cart = self._cart()
        key = str(product_id)
        if key in cart:
            if cart[key]["qty"] > 1:
                cart[key]["qty"] -= 1
            else:
                del cart[key]

    def clear(self) -> None:
        self._data["cart"] = {}

    def items(self) -> list[dict]:
        return [
            {"product_id": int(k), **v}
            for k, v in self._cart().items()
        ]

    def total(self) -> float:
        return sum(item["price"] * item["qty"] for item in self.items())

    def is_empty(self) -> bool:
        return len(self._cart()) == 0

    def count(self) -> int:
        return sum(item["qty"] for item in self.items())
