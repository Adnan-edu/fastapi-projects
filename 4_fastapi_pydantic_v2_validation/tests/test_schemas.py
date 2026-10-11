import pytest
from pydantic import ValidationError

from app.schemas.user import (
    Address,
    EmailNotification,
    NotificationPreference,
    SMSNotification,
    UserProfile,
    UserPublicResponse,
    UserRegister,
    UserUpdate,
    notification_adapter,
    user_register_adapter,
)


class TestFieldValidatorEmail:
    def test_valid_email(self):
        user = UserRegister(
            username="johndoe",
            email="john@example.com",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
        )
        assert user.email == "john@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(
                username="johndoe",
                email="not-an-email",
                password="Str0ng!Pass",
                confirm_password="Str0ng!Pass",
                first_name="John",
                last_name="Doe",
            )
        assert any("email" in str(err).lower() for err in exc_info.value.errors())

    def test_empty_email(self):
        with pytest.raises(ValidationError):
            UserRegister(
                username="johndoe",
                email="",
                password="Str0ng!Pass",
                confirm_password="Str0ng!Pass",
                first_name="John",
                last_name="Doe",
            )


class TestFieldValidatorPassword:
    def test_password_requires_uppercase(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="weak1!pass",
                confirm_password="weak1!pass",
                first_name="John",
                last_name="Doe",
            )
        assert "uppercase" in str(exc_info.value).lower()

    def test_password_requires_digit(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="Weak!!pass",
                confirm_password="Weak!!pass",
                first_name="John",
                last_name="Doe",
            )
        assert "digit" in str(exc_info.value).lower()

    def test_password_requires_special_char(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="Weak123Pass",
                confirm_password="Weak123Pass",
                first_name="John",
                last_name="Doe",
            )
        assert "special" in str(exc_info.value).lower()

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="Ab1!",
                confirm_password="Ab1!",
                first_name="John",
                last_name="Doe",
            )

    def test_strong_password_accepted(self):
        user = UserRegister(
            username="johndoe",
            email="john@example.com",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
        )
        assert user.password == "Str0ng!Pass"


class TestModelValidatorPasswordConfirmation:
    def test_passwords_match(self):
        user = UserRegister(
            username="johndoe",
            email="john@example.com",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
        )
        assert user.password == user.confirm_password

    def test_passwords_do_not_match(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="Str0ng!Pass",
                confirm_password="Different1!",
                first_name="John",
                last_name="Doe",
            )
        assert "do not match" in str(exc_info.value).lower()


class TestConfigDict:
    def test_str_strip_whitespace(self):
        user = UserRegister(
            username="  johndoe  ",
            email="john@example.com",
            password="  Str0ng!Pass  ",
            confirm_password="  Str0ng!Pass  ",
            first_name="  John  ",
            last_name="  Doe  ",
        )
        assert user.username == "johndoe"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.password == "Str0ng!Pass"

    def test_populate_by_name(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            firstName="John",
            lastName="Doe",
        )
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"

    def test_populate_by_field_name(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"


class TestFieldAlias:
    def test_alias_serialization(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            phone="+14155551234",
        )
        data = profile.model_dump(by_alias=True)
        assert "firstName" in data
        assert "lastName" in data
        assert "phoneNumber" in data

    def test_field_alias_in_json(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        json_str = profile.model_dump_json(by_alias=True)
        assert '"firstName"' in json_str
        assert '"lastName"' in json_str


class TestComputedField:
    def test_full_name_computed_field(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        assert profile.full_name == "John Doe"

    def test_display_name_computed_field(self):
        resp = UserPublicResponse(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        assert resp.display_name == "John Doe"

    def test_computed_field_in_serialization(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        data = profile.model_dump()
        assert data["full_name"] == "John Doe"


class TestFieldSerializer:
    def test_phone_masking_json(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            phone="+14155551234",
        )
        json_data = profile.model_dump(mode="json")
        assert json_data["phone"] == "***-***-1234"

    def test_phone_masking_python_mode(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            phone="+14155551234",
        )
        data = profile.model_dump(mode="python")
        assert data["phone"] == "+14155551234"

    def test_phone_masking_none(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            phone=None,
        )
        json_data = profile.model_dump(mode="json")
        assert json_data["phone"] is None


class TestTypeAdapter:
    def test_validate_list_of_users(self):
        raw_data = [
            {
                "username": "user1",
                "email": "user1@example.com",
                "password": "Str0ng!Pass",
                "confirm_password": "Str0ng!Pass",
                "first_name": "User",
                "last_name": "One",
            },
            {
                "username": "user2",
                "email": "user2@example.com",
                "password": "An0ther!Pass",
                "confirm_password": "An0ther!Pass",
                "first_name": "User",
                "last_name": "Two",
            },
        ]
        result = user_register_adapter.validate_python(raw_data)
        assert len(result) == 2
        assert result[0].username == "user1"
        assert result[1].username == "user2"

    def test_validate_list_invalid_item(self):
        raw_data = [
            {
                "username": "user1",
                "email": "bad-email",
                "password": "Str0ng!Pass",
                "confirm_password": "Str0ng!Pass",
                "first_name": "User",
                "last_name": "One",
            },
        ]
        with pytest.raises(ValidationError):
            user_register_adapter.validate_python(raw_data)

    def test_type_adapter_json_schema(self):
        schema = user_register_adapter.json_schema()
        assert "items" in schema or "$defs" in str(schema)


class TestDiscriminatedUnion:
    def test_email_notification_via_adapter(self):
        pref = notification_adapter.validate_python(
            {"type": "email", "email_address": "test@example.com"}
        )
        assert isinstance(pref, EmailNotification)
        assert pref.email_address == "test@example.com"

    def test_sms_notification_via_adapter(self):
        pref = notification_adapter.validate_python(
            {"type": "sms", "phone_number": "+14155551234"}
        )
        assert isinstance(pref, SMSNotification)
        assert pref.phone_number == "+14155551234"

    def test_invalid_type_via_adapter(self):
        with pytest.raises(ValidationError):
            notification_adapter.validate_python({"type": "push", "device_token": "abc123"})

    def test_direct_email_notification_model(self):
        pref = EmailNotification(type="email", email_address="test@example.com")
        assert pref.email_address == "test@example.com"

    def test_direct_sms_notification_model(self):
        pref = SMSNotification(type="sms", phone_number="+14155551234")
        assert pref.phone_number == "+14155551234"

    def test_notification_adapter_json_email(self):
        result = notification_adapter.validate_json(
            '{"type": "email", "email_address": "test@example.com"}'
        )
        assert isinstance(result, EmailNotification)

    def test_notification_adapter_json_sms(self):
        result = notification_adapter.validate_json(
            '{"type": "sms", "phone_number": "+14155551234"}'
        )
        assert isinstance(result, SMSNotification)


class TestNestedModels:
    def test_valid_address(self):
        addr = Address(
            street="123 Main St",
            city="Springfield",
            state="IL",
            zip_code="62701",
        )
        assert addr.city == "Springfield"
        assert addr.country == "US"

    def test_address_invalid_zip(self):
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Springfield",
                state="IL",
                zip_code="invalid",
            )

    def test_address_invalid_state_code(self):
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Springfield",
                state="Illinois",
                zip_code="62701",
            )

    def test_nested_address_in_user_registration(self):
        user = UserRegister(
            username="johndoe",
            email="john@example.com",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
            address={
                "street": "123 Main St",
                "city": "Springfield",
                "state": "IL",
                "zip_code": "62701",
            },
        )
        assert user.address is not None
        assert user.address.city == "Springfield"

    def test_nested_address_invalid_in_user_registration(self):
        with pytest.raises(ValidationError):
            UserRegister(
                username="johndoe",
                email="john@example.com",
                password="Str0ng!Pass",
                confirm_password="Str0ng!Pass",
                first_name="John",
                last_name="Doe",
                address={
                    "street": "123 Main St",
                    "city": "Springfield",
                    "state": "IL",
                    "zip_code": "bad",
                },
            )


class TestUserUpdate:
    def test_partial_update_all_none(self):
        update = UserUpdate()
        assert update.first_name is None
        assert update.last_name is None
        assert update.email is None
        assert update.phone is None

    def test_partial_update_some_fields(self):
        update = UserUpdate(first_name="Jane", email="jane@example.com")
        assert update.first_name == "Jane"
        assert update.last_name is None
        assert update.email == "jane@example.com"

    def test_model_dump_exclude_none(self):
        update = UserUpdate(first_name="Jane")
        data = update.model_dump(exclude_none=True)
        assert "first_name" in data
        assert "last_name" not in data


class TestEdgeCases:
    def test_username_pattern_rejects_special_chars(self):
        with pytest.raises(ValidationError):
            UserRegister(
                username="john@doe",
                email="john@example.com",
                password="Str0ng!Pass",
                confirm_password="Str0ng!Pass",
                first_name="John",
                last_name="Doe",
            )

    def test_username_pattern_accepts_underscores(self):
        user = UserRegister(
            username="john_doe",
            email="john@example.com",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
        )
        assert user.username == "john_doe"

    def test_address_default_country(self):
        addr = Address(
            street="123 Main St",
            city="Springfield",
            state="IL",
            zip_code="62701",
        )
        assert addr.country == "US"

    def test_phone_masking_short_digits(self):
        profile = UserProfile(
            id=1,
            username="johndoe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            phone="123",
        )
        json_data = profile.model_dump(mode="json")
        assert json_data["phone"] == "***-***-****"

    def test_email_domain_normalization(self):
        user = UserRegister(
            username="johndoe",
            email="John@Example.COM",
            password="Str0ng!Pass",
            confirm_password="Str0ng!Pass",
            first_name="John",
            last_name="Doe",
        )
        assert user.email == "John@example.com"