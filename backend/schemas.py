from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class PickLine(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    batch_id:str=Field(min_length=1,max_length=36)
    quantity:str|int
    lot:str|None=None
    expiry_date:str|None=None

class StockRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    type:Literal['receipt','opening','issue','customer_return','supplier_return','write_off','adjustment','reversal']
    product_id:str=Field(min_length=1,max_length=36)
    reason:str=Field(min_length=1,max_length=2000)
    quantity:str|int|None=None
    lot:str=Field(default='',max_length=100)
    expiry_date:str|None=None
    manufacture_date:str|None=None
    supplier:str=Field(default='',max_length=200)
    location:str=Field(default='',max_length=100)
    reference:str=Field(default='',max_length=200)
    batch_id:str|None=None
    direction:Literal['add','remove']|None=None
    expected_lines:list[PickLine]|None=Field(default=None,max_length=500)
    source_issue:str|None=None
    movement_id:str|None=None
