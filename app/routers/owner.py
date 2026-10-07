"""RESTAMP Owner V1 — property listing management routes.

Endpoints:
  POST /owner/listings       — create a new property listing (OWNER role required)
  GET  /owner/listings       — list caller's own listings (all statuses)
  GET  /owner/listings/{id}  — single owner listing detail

No admin endpoints here; see users.py for admin grants.
No schema changes; all writes use existing property_listings / physical_properties tables.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..deps import require_owner
from ..services import owner_listings as owner_svc

router = APIRouter(prefix="/owner", tags=["owner"])


@router.post("/listings", response_model=schemas.OwnerListingOut, status_code=201)
def create_listing(
    body: schemas.OwnerListingCreate,
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    """Create a new property listing. Lands in PENDING / AVAILABLE state."""
    price_paise = body.price_rupees * 100
    listing = owner_svc.create_owner_listing(
        db=db,
        owner_id=owner_id,
        title=body.title,
        transaction_type=body.transaction_type,
        property_type=body.property_type,
        price_paise=price_paise,
        price_period=body.price_period,
        locality=body.locality,
        city=body.city,
        pincode=body.pincode,
        address_line=body.address_line,
        area_value=body.area_value,
        area_unit=body.area_unit,
        bedrooms=body.bedrooms,
        bathrooms=body.bathrooms,
        description=body.description,
        construction_status=body.construction_status,
        image_urls=body.images,
    )
    db.commit()
    db.refresh(listing)

    # Build the response dict using the same reader
    card = owner_svc.get_owner_listing(db, owner_id, listing.id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")
    return card


@router.get("/listings", response_model=schemas.OwnerListingsResponse)
def list_my_listings(
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List all listings posted by the authenticated owner."""
    items, total = owner_svc.list_owner_listings(db, owner_id, page, page_size)
    return schemas.OwnerListingsResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/listings/{listing_id}", response_model=schemas.OwnerListingOut)
def get_my_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    """Get a single listing detail; returns 404 if not owned by caller."""
    card = owner_svc.get_owner_listing(db, owner_id, listing_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return card
