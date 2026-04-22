"""Wallet routes for Polymarket wallet configuration."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.user import User
from src.models.wallet import Wallet
from src.schemas.wallet import (
    WalletCreate,
    WalletUpdate,
    WalletResponse,
    WalletTestResponse,
    WalletListResponse,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.crypto import encrypt_private_key, decrypt_private_key

router = APIRouter(prefix="/api/wallets", tags=["wallets"])


def validate_private_key(private_key: str) -> tuple[bool, tuple[str, str] | str]:
    """Validate private key format and derive address.

    Returns:
        Tuple of (is_valid, (address, normalized_key) or error_message)
    """
    if not private_key:
        return False, "Private key is required"

    # Strip all whitespace/newlines
    normalized_key = "".join(private_key.split())

    # Remove optional 0x prefix for validation
    if normalized_key.startswith("0x"):
        hex_part = normalized_key[2:]
    else:
        hex_part = normalized_key

    # Core private key: 64 hex chars
    if len(hex_part) != 64:
        return False, f"Private key must be 64 hex characters, got {len(hex_part)}"

    try:
        int(hex_part, 16)
    except ValueError:
        return False, "Private key contains invalid hex characters"

    # Normalize to 0x prefix for downstream compatibility
    normalized_key = "0x" + hex_part
    address = "0x" + hex_part[:40]
    return True, (address, normalized_key)


@router.get("", response_model=ApiResponse[WalletListResponse])
async def list_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all wallets for the current user."""
    offset = (page - 1) * page_size

    result = await db.execute(
        select(Wallet)
        .where(Wallet.user_id == current_user.id)
        .offset(offset)
        .limit(page_size)
    )
    wallets = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(Wallet).where(Wallet.user_id == current_user.id)
    )
    total = len(count_result.scalars().all())
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ApiResponse(
        success=True,
        data=WalletListResponse(
            items=[WalletResponse.model_validate(w) for w in wallets],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.post("", response_model=ApiResponse[WalletResponse], status_code=status.HTTP_201_CREATED)
async def create_wallet(
    request: WalletCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new Polymarket wallet."""
    # Validate private key
    is_valid, result = validate_private_key(request.private_key)
    if not is_valid:
        from src.core.exceptions import ValidationError
        raise ValidationError(result)

    # result is now (address, normalized_key)
    address, normalized_key = result

    # If setting as default, unset other defaults
    if request.is_default if hasattr(request, 'is_default') else False:
        await db.execute(
            select(Wallet).where(
                and_(
                    Wallet.user_id == current_user.id,
                    Wallet.is_default == True,
                )
            )
        )

    # Encrypt private key (use normalized key)
    encrypted_key = encrypt_private_key(normalized_key)

    wallet = Wallet(
        user_id=current_user.id,
        name=request.name,
        address=address,
        private_key_encrypted=encrypted_key,
        proxy_wallet_address=request.proxy_wallet_address,
        is_default=request.is_default if hasattr(request, 'is_default') else False,
        status="active",
    )

    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    return ApiResponse(
        success=True,
        data=WalletResponse.model_validate(wallet),
        message="Wallet created successfully",
    )


@router.get("/{wallet_id}", response_model=ApiResponse[WalletResponse])
async def get_wallet(
    wallet_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific wallet."""
    result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.id == wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Wallet not found")

    return ApiResponse(
        success=True,
        data=WalletResponse.model_validate(wallet),
    )


@router.put("/{wallet_id}", response_model=ApiResponse[WalletResponse])
async def update_wallet(
    wallet_id: UUID,
    request: WalletUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a wallet."""
    result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.id == wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Wallet not found")

    # If setting as default, unset other defaults
    if request.is_default and not wallet.is_default:
        all_result = await db.execute(
            select(Wallet).where(
                and_(
                    Wallet.user_id == current_user.id,
                    Wallet.is_default == True,
                    Wallet.id != wallet_id,
                )
            )
        )
        for w in all_result.scalars().all():
            w.is_default = False

    # Update fields
    if request.name is not None:
        wallet.name = request.name
    if request.private_key is not None:
        # Validate new private key
        is_valid, result = validate_private_key(request.private_key)
        if not is_valid:
            from src.core.exceptions import ValidationError
            raise ValidationError(result)
        # result is (address, normalized_key)
        address, normalized_key = result
        wallet.address = address
        wallet.private_key_encrypted = encrypt_private_key(normalized_key)
    if request.proxy_wallet_address is not None:
        wallet.proxy_wallet_address = request.proxy_wallet_address
    if request.is_active is not None:
        wallet.is_active = request.is_active
    if request.is_default is not None:
        wallet.is_default = request.is_default

    await db.commit()
    await db.refresh(wallet)

    return ApiResponse(
        success=True,
        data=WalletResponse.model_validate(wallet),
        message="Wallet updated successfully",
    )


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a wallet."""
    result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.id == wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Wallet not found")

    await db.delete(wallet)
    await db.commit()


@router.post("/{wallet_id}/test", response_model=ApiResponse[WalletTestResponse])
async def test_wallet(
    wallet_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Test a wallet connection and get balance."""
    result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.id == wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Wallet not found")

    # Decrypt private key
    private_key = decrypt_private_key(wallet.private_key_encrypted or "")

    if not private_key:
        return ApiResponse(
            success=False,
            data=WalletTestResponse(
                success=False,
                message="Failed to decrypt private key",
                error="Decryption failed",
            ),
        )

    # Validate and derive address
    is_valid, result = validate_private_key(private_key)
    if not is_valid:
        wallet.status = "error"
        wallet.last_error = result
        wallet.error_count += 1
        await db.commit()
        return ApiResponse(
            success=False,
            data=WalletTestResponse(
                success=False,
                message="Invalid private key",
                error=result,
            ),
        )

    # result is (address, normalized_key)
    derived_address, normalized_key = result

    # Try to get proxy wallet USDC balance on-chain
    balance = None
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

        # 1. 初始化 ClobClient（用于验证私钥有效性）
        clob_kwargs = {
            "host": "https://clob.polymarket.com",
            "key": normalized_key,
            "chain_id": 137,
        }
        if wallet.proxy_wallet_address:
            clob_kwargs["signature_type"] = 2
            clob_kwargs["funder"] = wallet.proxy_wallet_address

        client = ClobClient(**clob_kwargs)
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)

        # 2. 查 proxy wallet 链上 USDC 余额
        proxy = wallet.proxy_wallet_address
        if proxy:
            import httpx

            # USDC 合约地址 (Polygon)
            USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            # balanceOf(address) selector
            data = "0x70a08231" + proxy.lower().replace("0x", "").zfill(64)

            # 尝试多个公共 RPC，避免单点故障
            rpc_urls = [
                "https://rpc.ankr.com/polygon",
                "https://polygon-bor-rpc.publicnode.com",
                "https://polygon.llamarpc.com",
            ]
            result = None
            last_err = None
            for rpc_url in rpc_urls:
                try:
                    resp = httpx.post(
                        rpc_url,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_call",
                            "params": [
                                {"to": USDC_CONTRACT, "data": data},
                                "latest",
                            ],
                        },
                        timeout=15,
                    )
                    resp.raise_for_status()
                    rpc_result = resp.json()
                    # HTTP 200 不代表 RPC 成功，检查 JSON body 里是否有 error
                    if "error" not in rpc_result and "result" in rpc_result:
                        result = rpc_result
                        break
                    last_err = RuntimeError(f"{rpc_url} RPC error: {rpc_result.get('error')}")
                except Exception as e:
                    last_err = e
                    continue

            if result is None:
                raise last_err or RuntimeError("All Polygon RPC endpoints failed")
            raw_hex = result.get("result", "0x0")
            raw_balance = int(raw_hex, 16) if raw_hex.startswith("0x") else 0
            # USDC 有 6 位小数
            balance = str(raw_balance / 1_000_000)
        else:
            # 没有 proxy 地址，退回到 CLOB allowance（仅作参考）
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            result = client.get_balance_allowance(params)
            raw_balance = result.get("balance", 0) if isinstance(result, dict) else 0
            balance = str(float(raw_balance) / 1_000_000)

        wallet.usdc_balance = balance
        wallet.status = "active"
        wallet.last_error = None
        wallet.last_used_at = str(datetime.utcnow())
    except Exception as e:
        wallet.status = "error"
        wallet.last_error = str(e)
        wallet.error_count += 1

    await db.commit()

    if wallet.status == "active":
        return ApiResponse(
            success=True,
            data=WalletTestResponse(
                success=True,
                message="Wallet connected successfully",
                address=derived_address,
                balance=balance,
            ),
        )
    else:
        return ApiResponse(
            success=False,
            data=WalletTestResponse(
                success=False,
                message="Failed to connect to Polymarket",
                address=derived_address,
                error=wallet.last_error,
            ),
        )


@router.post("/default/{wallet_id}/set", response_model=ApiResponse[WalletResponse])
async def set_default_wallet(
    wallet_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Set a wallet as the default."""
    result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.id == wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Wallet not found")

    # Unset other defaults
    all_result = await db.execute(
        select(Wallet).where(
            and_(
                Wallet.user_id == current_user.id,
                Wallet.is_default == True,
                Wallet.id != wallet_id,
            )
        )
    )
    for w in all_result.scalars().all():
        w.is_default = False

    # Set this as default
    wallet.is_default = True
    await db.commit()
    await db.refresh(wallet)

    return ApiResponse(
        success=True,
        data=WalletResponse.model_validate(wallet),
        message="Default wallet set successfully",
    )