import re
from datetime import datetime
from typing import List
from pydantic import BaseModel


class Package(BaseModel):
    height: int
    length: int
    weight: int
    width: int


class Product(BaseModel):
    productId: str
    category: str
    createdDate: datetime
    description: str
    modifiedDate: datetime
    name: str
    package: Package
    pictures: List[str]  # Changed from HttpUrl to str for simplicity
    price: int
    tags: List[str]


class Item(BaseModel):
    name: str
    quantity: int


class ItemList(BaseModel):
    products: List[Item]


def parse_raw_items(raw_data: List[str]) -> ItemList:
    # Join the list into a single string and normalize spacing
    raw_string = (
        " ".join(raw_data)
        .replace("[", "")
        .replace("]", "")
        .replace("{", "")
        .replace("}", "")
    )
    raw_string = re.sub(r"\s+", " ", raw_string).strip()

    # Find all items using regex
    matches = re.findall(r"name=([^,]+?)\s+quantity=(\d+)", raw_string)

    # Convert to structured data
    items = [
        Item(name=name.strip(), quantity=int(quantity)) for name, quantity in matches
    ]

    return ItemList(products=items)
