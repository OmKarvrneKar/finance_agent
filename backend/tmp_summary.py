
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.database import crud
from app.database.db import Account, User, get_db
from app.models.schemas import AccountCreate, AccountResponse, AccountUpdate, TransactionAccountAssign, TransactionResponse

router = APIRouter()
