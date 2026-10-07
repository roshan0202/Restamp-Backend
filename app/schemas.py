"""RESTAMP Phase 4 — request/response schemas (pydantic v2)."""
from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = r"^\+[1-9]\d{7,14}$"


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=500)


class UserOut(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None
    status: str


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("display_name cannot be empty or whitespace-only")
        if len(trimmed) > 255:
            raise ValueError("display_name cannot exceed 255 characters")
        return trimmed


class RoleSet(BaseModel):
    role: str = Field(pattern="^(BUYER|OWNER|BROKER)$")


class RoleOut(BaseModel):
    user_id: int
    role: str


class OTPRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)


class OTPVerify(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)
    code: str = Field(pattern=r"^\d{6}$")


class GoogleAuthIn(BaseModel):
    id_token: str = Field(min_length=1, max_length=4096)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    role: str | None


class MeOut(BaseModel):
    id: int
    display_name: str
    role: str | None
    providers: list[str]
    is_admin: bool


class AdminGrant(BaseModel):
    user_id: int


class ErrorOut(BaseModel):
    detail: str


# --- Buyer V1 public discovery (Phase 6B) -------------------------------------


class ListingCard(BaseModel):
    listing_id: int
    title: str
    price_paise: int
    price_period: str
    price_display: str
    transaction_type: str
    property_type: str
    construction_status: str | None
    description: str | None
    area_value: int | None
    area_unit: str | None
    bedrooms: int | None
    bathrooms: int | None
    address_line: str | None
    locality: str
    city: str
    pincode: str
    location_label: str
    cover_image_url: str | None


class ListingsResponse(BaseModel):
    items: list[ListingCard]
    page: int
    page_size: int
    total: int


class ListingDetail(ListingCard):
    gallery: list[str]
    verification_status: str
    listing_status: str


class ContactRevealOut(BaseModel):
    phone: str


class EnquiryCreate(BaseModel):
    property_listing_id: int
    message: str | None = Field(default=None, max_length=2000)


class EnquiryListingSnapshot(BaseModel):
    title: str
    price_paise: int
    price_period: str


class EnquiryOut(BaseModel):
    id: int
    property_listing_id: int
    message: str | None
    status: str
    closing_reason: str | None
    listing: EnquiryListingSnapshot


class EnquiriesResponse(BaseModel):
    items: list[EnquiryOut]
    page: int
    page_size: int
    total: int


# --- Owner V1 listing management (Phase 7) ------------------------------------

_TX_TYPES = {"BUY", "RESALE", "RENT", "LEASE"}
_PROP_TYPES = {"APARTMENT", "VILLA", "HOUSE", "COMMERCIAL", "PLOT", "AGRICULTURAL_LAND"}
_CONST_STATUSES = {"READY_TO_MOVE", "UNDER_CONSTRUCTION", "NEW_LAUNCH"}


class OwnerListingCreate(BaseModel):
    """Payload sent by the owner when posting a property."""

    title: str = Field(min_length=1, max_length=255)
    transaction_type: str = Field(default="BUY")
    property_type: str = Field(default="APARTMENT")
    price_rupees: int = Field(ge=1)  # frontend sends rupees; we convert to paise
    price_period: str = Field(default="TOTAL")  # TOTAL | MONTHLY
    description: str | None = Field(default=None, max_length=5000)
    construction_status: str | None = None
    # Location (free-text; service does best-effort lookup/create)
    locality: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=255)
    pincode: str = Field(min_length=1, max_length=10)
    address_line: str | None = Field(default=None, max_length=500)
    # Physical attributes
    area_value: int | None = Field(default=None, ge=1)
    area_unit: str | None = Field(default=None, max_length=20)
    bedrooms: int | None = Field(default=None, ge=0, le=99)
    bathrooms: int | None = Field(default=None, ge=0, le=99)
    # Media URLs
    images: list[str] = Field(default_factory=list)

    @field_validator("transaction_type")
    @classmethod
    def validate_tx(cls, v: str) -> str:
        u = v.upper()
        if u not in _TX_TYPES:
            raise ValueError(f"transaction_type must be one of {_TX_TYPES}")
        return u

    @field_validator("property_type")
    @classmethod
    def validate_prop(cls, v: str) -> str:
        u = v.upper()
        if u not in _PROP_TYPES:
            raise ValueError(f"property_type must be one of {_PROP_TYPES}")
        return u

    @field_validator("price_period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        u = v.upper()
        if u not in {"TOTAL", "MONTHLY"}:
            raise ValueError("price_period must be TOTAL or MONTHLY")
        return u

    @field_validator("construction_status")
    @classmethod
    def validate_const(cls, v: str | None) -> str | None:
        if v is None:
            return None
        u = v.upper()
        if u not in _CONST_STATUSES:
            raise ValueError(f"construction_status must be one of {_CONST_STATUSES}")
        return u


class OwnerListingOut(BaseModel):
    """A listing row visible to its owner (all statuses, no enquiry data)."""

    listing_id: int
    title: str
    transaction_type: str
    property_type: str
    price_paise: int
    price_period: str
    price_display: str
    construction_status: str | None
    verification_status: str
    listing_status: str
    description: str | None
    locality: str
    city: str
    pincode: str
    address_line: str | None
    area_value: int | None
    area_unit: str | None
    bedrooms: int | None
    bathrooms: int | None
    cover_image_url: str | None
    gallery: list[str] = Field(default_factory=list)


class OwnerListingsResponse(BaseModel):
    items: list[OwnerListingOut]
    page: int
    page_size: int
    total: int
