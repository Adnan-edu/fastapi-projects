from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic import EmailStr


class Address(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    street: str = Field(..., min_length=1, max_length=200, description="Street address")
    city: str = Field(..., min_length=1, max_length=100, description="City name")
    state: str = Field(..., min_length=2, max_length=2, description="2-letter state code")
    zip_code: str = Field(
        ..., pattern=r"^\d{5}(-\d{4})?$", description="US ZIP code (e.g. 12345 or 12345-6789)"
    )
    country: str = Field(default="US", max_length=2, description="2-letter country code")


class UserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(
        ..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$",
        description="Alphanumeric username (underscores allowed)",
    )
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Password (8+ chars, 1 uppercase, 1 digit, 1 special char)",
    )
    confirm_password: str = Field(
        ..., min_length=8, max_length=128,
        description="Must match password",
    )
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    address: Address | None = Field(default=None, description="Optional mailing address")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors = []
        if not any(c.isupper() for c in v):
            errors.append("must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/`~" for c in v):
            errors.append("must contain at least one special character")
        if errors:
            raise ValueError("Password " + ", ".join(errors))
        return v

    @model_validator(mode="after")
    def verify_passwords_match(self) -> "UserRegister":
        if self.password != self.confirm_password:
            raise ValueError("passwords do not match")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{7,15}$")
    address: Address | None = Field(default=None)


class EmailNotification(BaseModel):
    type: Literal["email"]
    email_address: EmailStr


class SMSNotification(BaseModel):
    type: Literal["sms"]
    phone_number: str = Field(pattern=r"^\+?\d{7,15}$")


NotificationPreference = Annotated[
    Union[EmailNotification, SMSNotification],
    Field(discriminator="type"),
]


class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    first_name: str
    last_name: str

    @computed_field
    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class UserProfile(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: int
    username: str
    email: EmailStr
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    phone: str | None = Field(default=None, alias="phoneNumber")
    address: Address | None = Field(default=None)

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @field_serializer("phone", when_used="json")
    @classmethod
    def mask_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 7:
            return "***-***-****"
        last_four = digits[-4:]
        return f"***-***-{last_four}"


user_register_adapter = TypeAdapter(list[UserRegister])
notification_adapter = TypeAdapter(NotificationPreference)