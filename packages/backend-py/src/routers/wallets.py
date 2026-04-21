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


def validate_private_key(private_key: str) -> tuple[bool, Optional[str]]:
    """Validate private key format and derive address.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not private_key:
        return False, "Private key is required"

    # Check 0x prefix
    if not private_key.startswith("0x"):
        return False, "Private key must start with 0x"

    # Check length (64 hex chars + 0x prefix = 66)
    if len(private_key) != 66:
        return False, f"Private key must be 66 characters, got {len(private_key)}"

    # Check hex characters
    hex_part = private_key[2:]
    try:
        int(hex_part, 16)
    except ValueError:
        return False, "Private key contains invalid hex characters"

    # Derive address (simplified - just use first 40 chars as address)
    address = "0x" + hex_part[:40]
    return True, address


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

    return ApiResponse(
        success=True,
        data=WalletListResponse(
            items=[WalletResponse.model_validate(w) for w in wallets],
            total=total,
            page=page,
            page_size=page_size,
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

    address = result

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

    # Encrypt private key
    encrypted_key = encrypt_private_key(request.private_key)

    wallet = Wallet(
        user_id=current_user.id,
        name=request.name,
        address=address,
        private_key_encrypted=encrypted_key,
        proxy_url=request.proxy_url,
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
        wallet.address = result
        wallet.private_key_encrypted = encrypt_private_key(request.private_key)
    if request.proxy_url is not None:
        wallet.proxy_url = request.proxy_url
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
    is_valid, validation_result = validate_private_key(private_key)
    if not is_valid:
        wallet.status = "error"
        wallet.last_error = validation_result
        wallet.error_count += 1
        await db.commit()
        return ApiResponse(
            success=False,
            data=WalletTestResponse(
                success=False,
                message="Invalid private key",
                error=validation_result,
            ),
        )

    derived_address = validation_result

    # Try to get balance from Polymarket
    balance = None
    try:
        from src.polymarket import get_client

        client = get_client(
            private_key=private_key,
            proxy=wallet.proxy_url,
        )
        balance_obj = client.get_balance()
        balance = str(balance_obj.usdc_balance)
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