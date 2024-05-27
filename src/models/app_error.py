from flask import request
from openai import BaseModel


class AppError(BaseModel):
    request_id: int
    error_code: int
