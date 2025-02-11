import re
import os
from http.client import HTTPException
from time import time
from datetime import datetime
from typing import List
import boto3
import stripe
from pydantic import EmailStr, ValidationError, BaseModel, HttpUrl


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
    pictures: List[HttpUrl]
    price: int
    tags: List[str]

class Item(BaseModel):
    name: str
    quantity: int
    unit: str

class ItemList(BaseModel):
    products: List[Item]




def parse_raw_items(raw_data: List[str]) -> ItemList:
    # Join the list into a single string and normalize spacing
    raw_string = " ".join(raw_data).replace("[", "").replace("]", "").replace("{", "").replace("}", "")
    raw_string = re.sub(r'\s+', ' ', raw_string).strip()

    # Find all items using regex
    matches = re.findall(r"name=([^,]+?)\s+quantity=(\d+)\s+unit=([a-zA-Z]+)", raw_string)

    # Convert to structured data
    items = [Item(name=name.strip(), quantity=int(quantity), unit=unit.strip()) for name, quantity, unit in matches]

    return ItemList(products=items)