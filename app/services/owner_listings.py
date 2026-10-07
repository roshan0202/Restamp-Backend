"""RESTAMP Owner V1 — listing creation and management.

An owner can create a property listing (PhysicalProperty + PropertyListing +
PropertyMedia rows) and retrieve their own listings.

Location strategy:
  1. Try to find an exact postcode match by pincode.
  2. Fall back to a case-insensitive locality name match.
  3. If neither exists, auto-create the full location chain so the submission
     never fails for a valid but unseen locality — the admin can clean/merge
     location data independently.

New listings land in PENDING/AVAILABLE state; verification is done by admin.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.locations import City, District, Locality, Postcode, Taluk, Village
from ..models.properties import PhysicalProperty, PropertyListing, PropertyMedia
from ..services.listings import format_price


# ---------------------------------------------------------------------------
# Location helpers
# ---------------------------------------------------------------------------


def _find_or_create_postcode(db: Session, city: str, locality: str, pincode: str) -> int:
    """Return postcode.id; creates the chain if the pincode is not in the DB."""
    # 1. Exact pincode match
    row = db.query(Postcode).filter(Postcode.pincode == pincode.strip()).first()
    if row:
        return row.id

    # 2. Locality-name match (case-insensitive) — use first postcode in that locality
    row = (
        db.query(Postcode)
        .join(Locality, Postcode.locality_id == Locality.id)
        .filter(func.lower(Locality.name) == locality.strip().lower())
        .first()
    )
    if row:
        return row.id

    # 3. Create the full chain for this new location
    city_name = city.strip() or "Unknown City"
    locality_name = locality.strip() or "Unknown Locality"
    pincode_val = (pincode.strip() or "000000")[:10]

    city_row = db.query(City).filter(func.lower(City.name) == city_name.lower()).first()
    if not city_row:
        city_row = City(name=city_name)
        db.add(city_row)
        db.flush()

    dist_row = (
        db.query(District)
        .filter(District.city_id == city_row.id, func.lower(District.name) == city_name.lower())
        .first()
    )
    if not dist_row:
        dist_row = District(city_id=city_row.id, name=city_name)
        db.add(dist_row)
        db.flush()

    taluk_row = (
        db.query(Taluk)
        .filter(Taluk.district_id == dist_row.id, func.lower(Taluk.name) == locality_name.lower())
        .first()
    )
    if not taluk_row:
        taluk_row = Taluk(district_id=dist_row.id, name=locality_name)
        db.add(taluk_row)
        db.flush()

    village_row = (
        db.query(Village)
        .filter(Village.taluk_id == taluk_row.id, func.lower(Village.name) == locality_name.lower())
        .first()
    )
    if not village_row:
        village_row = Village(taluk_id=taluk_row.id, name=locality_name)
        db.add(village_row)
        db.flush()

    loc_row = (
        db.query(Locality)
        .filter(Locality.village_id == village_row.id, func.lower(Locality.name) == locality_name.lower())
        .first()
    )
    if not loc_row:
        loc_row = Locality(village_id=village_row.id, name=locality_name)
        db.add(loc_row)
        db.flush()

    pc_row = (
        db.query(Postcode)
        .filter(Postcode.locality_id == loc_row.id, Postcode.pincode == pincode_val)
        .first()
    )
    if not pc_row:
        pc_row = Postcode(locality_id=loc_row.id, pincode=pincode_val)
        db.add(pc_row)
        db.flush()

    return pc_row.id


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_owner_listing(
    db: Session,
    owner_id: int,
    title: str,
    transaction_type: str,
    property_type: str,
    price_paise: int,
    price_period: str,
    locality: str,
    city: str,
    pincode: str,
    address_line: str | None,
    area_value: int | None,
    area_unit: str | None,
    bedrooms: int | None,
    bathrooms: int | None,
    description: str | None,
    construction_status: str | None,
    image_urls: list[str],
) -> PropertyListing:
    """Creates PhysicalProperty + PropertyListing + PropertyMedia rows atomically."""
    postcode_id = _find_or_create_postcode(db, city, locality, pincode)

    phys = PhysicalProperty(
        postcode_id=postcode_id,
        user_id=owner_id,
        address_line=address_line,
        area_value=area_value,
        area_unit=area_unit,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
    )
    db.add(phys)
    db.flush()  # get phys.id

    listing = PropertyListing(
        physical_property_id=phys.id,
        user_id=owner_id,
        title=title,
        price_paise=price_paise,
        price_period=price_period,
        description=description,
        construction_status=construction_status,
        transaction_type=transaction_type,
        property_type=property_type,
        verification_status="PENDING",
        listing_status="AVAILABLE",
    )
    db.add(listing)
    db.flush()  # get listing.id

    for idx, url in enumerate(image_urls):
        if url:
            media = PropertyMedia(
                property_listing_id=listing.id,
                url=url,
                media_type="IMAGE",
                order_index=idx,
                uploaded_by=owner_id,
            )
            db.add(media)

    db.flush()
    return listing


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _owner_listing_query(db: Session, owner_id: int):
    from ..models.locations import City, District, Locality, Postcode, Taluk, Village

    return (
        db.query(
            PropertyListing,
            PhysicalProperty.address_line,
            PhysicalProperty.area_value,
            PhysicalProperty.area_unit,
            PhysicalProperty.bedrooms,
            PhysicalProperty.bathrooms,
            Locality.name.label("locality"),
            City.name.label("city"),
            Postcode.pincode,
        )
        .join(PhysicalProperty, PropertyListing.physical_property_id == PhysicalProperty.id)
        .join(Postcode, PhysicalProperty.postcode_id == Postcode.id)
        .join(Locality, Postcode.locality_id == Locality.id)
        .join(Village, Locality.village_id == Village.id)
        .join(Taluk, Village.taluk_id == Taluk.id)
        .join(District, Taluk.district_id == District.id)
        .join(City, District.city_id == City.id)
        .filter(PropertyListing.user_id == owner_id)
    )


def _row_to_dict(row) -> dict:
    listing, address_line, area_value, area_unit, bedrooms, bathrooms, locality, city, pincode = row
    return {
        "listing_id": listing.id,
        "title": listing.title,
        "transaction_type": listing.transaction_type,
        "property_type": listing.property_type,
        "price_paise": listing.price_paise,
        "price_period": listing.price_period,
        "price_display": format_price(listing.price_paise, listing.price_period),
        "construction_status": listing.construction_status,
        "verification_status": listing.verification_status,
        "listing_status": listing.listing_status,
        "description": listing.description,
        "address_line": address_line,
        "locality": locality or "",
        "city": city or "",
        "pincode": pincode or "",
        "area_value": area_value,
        "area_unit": area_unit,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "cover_image_url": None,  # filled by caller
    }


def list_owner_listings(
    db: Session, owner_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    q = _owner_listing_query(db, owner_id)
    total = q.count()
    rows = q.order_by(PropertyListing.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    cards = [_row_to_dict(r) for r in rows]

    # Batch fetch cover images (first media per listing)
    if cards:
        listing_ids = [c["listing_id"] for c in cards]
        media_rows = (
            db.query(PropertyMedia.property_listing_id, PropertyMedia.url)
            .filter(
                PropertyMedia.property_listing_id.in_(listing_ids),
                PropertyMedia.order_index == 0,
            )
            .all()
        )
        cover_map = {r.property_listing_id: r.url for r in media_rows}
        for c in cards:
            c["cover_image_url"] = cover_map.get(c["listing_id"])

    return cards, total


def get_owner_listing(db: Session, owner_id: int, listing_id: int) -> dict | None:
    q = _owner_listing_query(db, owner_id).filter(PropertyListing.id == listing_id)
    row = q.first()
    if row is None:
        return None
    card = _row_to_dict(row)
    # Fetch all media for this listing
    media = (
        db.query(PropertyMedia.url)
        .filter(PropertyMedia.property_listing_id == listing_id)
        .order_by(PropertyMedia.order_index)
        .all()
    )
    urls = [m.url for m in media]
    card["cover_image_url"] = urls[0] if urls else None
    card["gallery"] = urls
    return card
