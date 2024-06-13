from fastapi import APIRouter
from node.utils import get_logger
from typing import Dict
from node.comms.user import register_user, check_user

logger = get_logger(__name__)

router = APIRouter()


@router.post("/RegisterUser")
async def register_user_http(user_input: Dict) -> Dict:
    return await register_user(user_input)


@router.post("/CheckUser")
async def check_user_http(user_input: Dict) -> Dict:
    return await check_user(user_input)

